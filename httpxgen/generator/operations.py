import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.naming import (
    argument_identifier,
    class_name,
    enum_member,
    identifier,
)
from httpxgen.generator.schema import is_object, schema_type, split_all_of
from httpxgen.openapi import (
    APIHeader,
    APIParameter,
    APIResponse,
    HttpMethod,
    MediaType,
    OpenAPISpec,
    PathItem,
    Reference,
    RequestBody,
    get_operation,
)

NO_DEFAULT = object()


@dataclass(frozen=True)
class Parameter:
    name: str
    wire_name: str
    location: str
    annotation: str
    required: bool
    style: str = "form"
    explode: bool = True
    allow_reserved: bool = False
    default: Any = NO_DEFAULT
    constraints: tuple[tuple[str, Any], ...] = ()
    default_source: str | None = None


@dataclass(frozen=True)
class MultipartField:
    name: str
    wire_name: str
    annotation: str
    required: bool
    is_file: bool = False
    is_array: bool = False
    content_type: str | None = None
    json_annotation: str | None = None


@dataclass(frozen=True)
class Body:
    annotation: str
    required: bool
    media_type: str = "application/json"
    kind: str = "json"
    binary_fields: tuple[str, ...] = ()
    multipart_fields: tuple[MultipartField, ...] = ()
    form_encodings: tuple[tuple[str, dict[str, Any]], ...] = ()


@dataclass(frozen=True)
class ResponseContent:
    annotation: str
    model_annotation: str | None
    kind: str
    media_type: str


@dataclass(frozen=True)
class ResponseHeader:
    name: str
    wire_name: str
    annotation: str


@dataclass(frozen=True)
class Response:
    status: int | str
    annotation: str
    model_annotation: str | None
    success: bool = True
    kind: str = "json"
    media_type: str | None = None
    contents: tuple[ResponseContent, ...] = ()
    headers: tuple[ResponseHeader, ...] = ()
    result_annotation: str | None = None


@dataclass(frozen=True)
class SecurityScheme:
    name: str
    kind: str
    location: str | None = None
    parameter_name: str | None = None
    prefix: str | None = None


@dataclass(frozen=True)
class Operation:
    method: HttpMethod
    path: str
    name: str
    parameters: tuple[Parameter, ...]
    body_annotation: str | None
    body_required: bool
    responses: tuple[Response, ...]
    body: Body | None = None
    security: tuple[tuple[str, ...], ...] = ()
    security_schemes: tuple[SecurityScheme, ...] = ()
    bodies: tuple[Body, ...] = ()


def read_operations(spec: OpenAPISpec) -> tuple[Operation, ...]:
    operations: list[Operation] = []
    schemes = read_security_schemes(spec)
    for path in sorted(spec.paths):
        path_item = _resolve_path_item(spec.paths[path], spec)
        for method in HttpMethod:
            operation = get_operation(path_item, method)
            if operation is None:
                continue
            if not operation.operation_id:
                raise GenerationError(f"{method.upper()} {path} has no operationId")
            bodies = _read_bodies(operation.request_body, spec)
            if len(bodies) > 1 and any(body.kind == "multipart" for body in bodies):
                raise GenerationError(
                    f"{method.upper()} {path} combines multipart/form-data with "
                    "other request media types; split it into separate operations"
                )
            body = bodies[0] if bodies else None
            parameters = _read_parameters(
                [*path_item.parameters, *operation.parameters], spec
            )
            _validate_parameters(path, parameters, has_body=body is not None)
            if body is not None and body.kind == "multipart":
                _validate_multipart_fields(path, parameters, body.multipart_fields)
            security_source = (
                spec.security if operation.security is None else operation.security
            )
            requirements = tuple(tuple(item) for item in security_source)
            unknown = sorted(
                {name for requirement in requirements for name in requirement}
                - {scheme.name for scheme in schemes}
            )
            if unknown:
                raise GenerationError(
                    f"{method.upper()} {path} references unknown security scheme(s): "
                    f"{', '.join(unknown)}"
                )
            operations.append(
                Operation(
                    method=method,
                    path=path,
                    name=identifier(operation.operation_id),
                    parameters=parameters,
                    body_annotation=(
                        None
                        if body is not None and body.kind == "multipart"
                        else " | ".join(
                            dict.fromkeys(item.annotation for item in bodies)
                        )
                        if bodies
                        else None
                    ),
                    body_required=(
                        body.required if body and body.kind != "multipart" else False
                    ),
                    responses=_read_responses(
                        operation.responses,
                        method,
                        path,
                        identifier(operation.operation_id),
                        spec,
                    ),
                    body=body,
                    security=requirements,
                    security_schemes=schemes,
                    bodies=bodies,
                )
            )

    names = [operation.name for operation in operations]
    if len(names) != len(set(names)):
        raise GenerationError("operationId values must be unique Python identifiers")
    return tuple(operations)


def query_parameters(operation: Operation) -> tuple[Parameter, ...]:
    return tuple(
        parameter for parameter in operation.parameters if parameter.location == "query"
    )


def query_model_name(operation: Operation) -> str:
    return f"{class_name(operation.name)}Params"


def _resolve_path_item(value: PathItem, spec: OpenAPISpec) -> PathItem:
    if value.ref is None:
        return value
    raw = _resolve_component(value.ref, "pathItems", spec.components.path_items)
    merged = {**raw, **value.model_dump(by_alias=True, exclude_none=True)}
    merged.pop("$ref", None)
    return PathItem.model_validate(merged)


def _resolve_parameter(
    value: APIParameter | Reference, spec: OpenAPISpec
) -> APIParameter:
    if isinstance(value, APIParameter):
        return value
    return APIParameter.model_validate(
        _resolve_component(value.ref, "parameters", spec.components.parameters)
    )


def _read_parameters(
    values: Sequence[APIParameter | Reference], spec: OpenAPISpec
) -> tuple[Parameter, ...]:
    resolved: dict[tuple[str, str], APIParameter] = {}
    for raw_value in values:
        value = _resolve_parameter(raw_value, spec)
        # Later operation parameters override path-level parameters.
        resolved[(value.name, value.location)] = value

    parameters: list[Parameter] = []
    for value in resolved.values():
        if value.location not in {"path", "query", "header", "cookie"}:
            raise GenerationError(f"unsupported parameter location: {value.location!r}")
        required = value.required or value.location == "path"
        schema = value.schema_
        if value.content:
            schema, _, _ = _select_media(value.content, "parameter", kinds=("json",))
        annotation = schema_type(schema)
        if (
            not required
            and schema.get("default", NO_DEFAULT) is NO_DEFAULT
            and "None" not in annotation
        ):
            annotation = f"{annotation} | None"
        style = value.style or (
            "form" if value.location in {"query", "cookie"} else "simple"
        )
        explode = value.explode if value.explode is not None else style == "form"
        parameters.append(
            Parameter(
                name=argument_identifier(value.name),
                wire_name=value.name,
                location=value.location,
                annotation=annotation,
                required=required,
                style=style,
                explode=explode,
                allow_reserved=value.allow_reserved,
                default=schema.get("default", NO_DEFAULT),
                constraints=_constraints(schema),
                default_source=_parameter_default_source(schema, spec),
            )
        )
    return tuple(parameters)


def _validate_parameters(
    path: str, parameters: Sequence[Parameter], *, has_body: bool
) -> None:
    names = [item.name for item in parameters]
    if len(names) != len(set(names)):
        raise GenerationError(f"{path} has parameter names that collide in Python")
    reserved = {"self", "timeout"} | ({"body"} if has_body else set())
    conflicts = sorted(reserved.intersection(names))
    if conflicts:
        raise GenerationError(
            f"{path} has parameter names reserved by the client: {', '.join(conflicts)}"
        )
    placeholders = set(re.findall(r"\{([^{}]+)\}", path))
    path_parameters = {item.wire_name for item in parameters if item.location == "path"}
    if placeholders != path_parameters:
        missing = sorted(placeholders - path_parameters)
        extra = sorted(path_parameters - placeholders)
        details = []
        if missing:
            details.append(f"missing path parameter(s): {', '.join(missing)}")
        if extra:
            details.append(f"unused path parameter(s): {', '.join(extra)}")
        raise GenerationError(f"{path}: {'; '.join(details)}")
    supported = {
        "path": {"simple", "label", "matrix"},
        "query": {"form", "spaceDelimited", "pipeDelimited", "deepObject"},
        "header": {"simple"},
        "cookie": {"form"},
    }
    for item in parameters:
        if item.style not in supported[item.location]:
            raise GenerationError(
                f"unsupported {item.location} parameter style: {item.style!r}"
            )


def _validate_multipart_fields(
    path: str,
    parameters: Sequence[Parameter],
    fields: Sequence[MultipartField],
) -> None:
    names = [field.name for field in fields]
    duplicates = {name for name in names if names.count(name) > 1}
    parameter_names = {parameter.name for parameter in parameters}
    reserved = {"self", "timeout", "body", "content_type"}
    conflicts = sorted(duplicates | (set(names) & (parameter_names | reserved)))
    if conflicts:
        raise GenerationError(
            f"{path} has multipart field names that collide with client parameters: "
            + ", ".join(conflicts)
        )


def _read_bodies(
    value: RequestBody | Reference | None, spec: OpenAPISpec
) -> tuple[Body, ...]:
    if value is None:
        return ()
    if isinstance(value, Reference):
        value = RequestBody.model_validate(
            _resolve_component(
                value.ref, "requestBodies", spec.components.request_bodies
            )
        )
    result: list[Body] = []
    for schema, media_type, kind in _media_options(
        value.content,
        "request body",
        kinds=("json", "form", "multipart", "text", "binary"),
    ):
        annotation = "BinaryContent" if kind == "binary" else schema_type(schema)
        shape = schema
        if "$ref" in schema:
            name = _reference_name(schema["$ref"], "schemas")
            shape = spec.components.schemas.get(name, schema)
        _, shape = split_all_of(shape)
        form_encodings = ()
        if kind == "form":
            if not is_object(shape):
                raise GenerationError(
                    "URL-encoded form bodies require an object schema"
                )
            encodings = value.content[media_type].encoding
            unknown = set(encodings) - set(shape.get("properties", {}))
            if unknown:
                raise GenerationError(
                    f"form encoding names unknown properties: {sorted(unknown)}"
                )
            form_fields = []
            for field_name, field_schema in shape.get("properties", {}).items():
                encoding = encodings.get(field_name, {})
                unsupported = set(encoding) - {
                    "style",
                    "explode",
                    "contentType",
                    "allowReserved",
                }
                if unsupported or encoding.get("allowReserved"):
                    raise GenerationError(
                        f"form field {field_name!r} uses unsupported encoding options"
                    )
                style = encoding.get("style", "form")
                explode = encoding.get("explode", style == "form")
                if style not in {
                    "form",
                    "spaceDelimited",
                    "pipeDelimited",
                    "deepObject",
                } or (style != "form" and explode != (style == "deepObject")):
                    raise GenerationError(
                        f"form field {field_name!r} uses unsupported "
                        "style/explode combination"
                    )
                content_type = encoding.get("contentType")
                shape_field = field_schema
                if "$ref" in shape_field:
                    shape_field = spec.components.schemas.get(
                        _reference_name(shape_field["$ref"], "schemas"), shape_field
                    )
                item_schema = shape_field.get("items", {})
                if "$ref" in item_schema:
                    item_schema = spec.components.schemas.get(
                        _reference_name(item_schema["$ref"], "schemas"), item_schema
                    )
                structured = is_object(shape_field) or (
                    shape_field.get("type") == "array" and is_object(item_schema)
                )
                uses_style = bool(set(encoding) & {"style", "explode", "allowReserved"})
                if uses_style:
                    invalid_shape = (
                        (style == "deepObject" and not is_object(shape_field))
                        or (
                            style in {"spaceDelimited", "pipeDelimited"}
                            and shape_field.get("type") != "array"
                        )
                        or (
                            shape_field.get("type") == "array"
                            and is_object(item_schema)
                        )
                    )
                    for nested in shape_field.get("properties", {}).values():
                        if "$ref" in nested:
                            nested = spec.components.schemas.get(
                                _reference_name(nested["$ref"], "schemas"), nested
                            )
                        invalid_shape |= (
                            is_object(nested) or nested.get("type") == "array"
                        )
                    if invalid_shape:
                        raise GenerationError(
                            f"form field {field_name!r} requires JSON content encoding "
                            "for nested values or a compatible style"
                        )
                json_content = not uses_style and (
                    structured
                    if content_type is None
                    else bool(
                        content_type
                        and (
                            content_type == "application/json"
                            or content_type.endswith("+json")
                        )
                    )
                )
                if (
                    not uses_style
                    and content_type
                    and (content_type != "text/plain" or structured)
                    and not json_content
                ):
                    raise GenerationError(
                        f"form field {field_name!r} has unsupported contentType "
                        f"{content_type!r}"
                    )
                form_fields.append(
                    (
                        field_name,
                        {"style": style, "explode": explode, "json": json_content},
                    )
                )
            form_encodings = tuple(form_fields)
        required_fields = set(shape.get("required", ()))
        multipart_fields: list[MultipartField] = []
        encodings = value.content[media_type].encoding if kind == "multipart" else {}
        unknown = set(encodings) - set(shape.get("properties", {}))
        if unknown:
            raise GenerationError(
                f"multipart encoding names unknown properties: {sorted(unknown)}"
            )
        for name, field in shape.get("properties", {}).items():
            is_array = field.get("type") == "array"
            item = field.get("items", {}) if is_array else field
            is_file = item.get("format") == "binary"
            encoding = encodings.get(name, {})
            unsupported = set(encoding) - {"contentType"}
            if unsupported:
                raise GenerationError(
                    f"multipart field {name!r} has unsupported encoding options: "
                    f"{sorted(unsupported)}"
                )
            item_shape = item
            if "$ref" in item:
                item_shape = spec.components.schemas.get(
                    _reference_name(item["$ref"], "schemas"), item
                )
            content_type = encoding.get("contentType")
            structured = is_object(item_shape)
            if content_type is None and structured:
                content_type = "application/json"
            json_encoded = content_type is not None and (
                content_type.split(";", 1)[0].lower() == "application/json"
                or content_type.split(";", 1)[0].lower().endswith("+json")
            )
            if (
                kind == "multipart"
                and not is_file
                and content_type
                and not json_encoded
                and (structured or content_type != "text/plain")
            ):
                raise GenerationError(
                    f"multipart field {name!r} has unsupported contentType "
                    f"{content_type!r}"
                )
            field_annotation = (
                "Sequence[UploadInput]"
                if is_file and is_array
                else "UploadInput"
                if is_file
                else schema_type(field)
            )
            multipart_fields.append(
                MultipartField(
                    name=argument_identifier(name),
                    wire_name=name,
                    annotation=field_annotation,
                    required=name in required_fields,
                    is_file=is_file,
                    is_array=is_array,
                    content_type=content_type,
                    json_annotation=schema_type(item)
                    if json_encoded and not is_file
                    else None,
                )
            )
        binary_fields = tuple(
            field.wire_name for field in multipart_fields if field.is_file
        )
        result.append(
            Body(
                annotation,
                value.required,
                media_type,
                kind,
                binary_fields,
                tuple(multipart_fields),
                form_encodings,
            )
        )
    return tuple(result)


def _read_responses(
    values: Mapping[str, APIResponse | Reference],
    method: HttpMethod,
    path: str,
    operation_name: str,
    spec: OpenAPISpec,
) -> tuple[Response, ...]:
    responses: list[Response] = []
    for status_text, raw_response in values.items():
        response = raw_response
        if isinstance(response, Reference):
            response = APIResponse.model_validate(
                _resolve_component(response.ref, "responses", spec.components.responses)
            )
        success = _is_success_status(status_text)
        headers = _read_response_headers(response.headers, spec, method, path)
        model_annotation: str | None = None
        if response.content:
            contents = tuple(
                ResponseContent(
                    annotation=_content_annotation(schema, kind),
                    model_annotation=_response_model(schema, spec.components.schemas),
                    kind=kind,
                    media_type=media_type,
                )
                for schema, media_type, kind in _media_options(
                    response.content,
                    "response",
                    kinds=("json", "text", "binary"),
                )
            )
            annotation = " | ".join(dict.fromkeys(item.annotation for item in contents))
            media_type, kind = contents[0].media_type, contents[0].kind
            if len(contents) == 1:
                model_annotation = contents[0].model_annotation
        else:
            contents = ()
            media_type, kind, annotation = None, "empty", "None"
        status: int | str = (
            int(status_text) if status_text.isdigit() else status_text.upper()
        )
        if not status_text.isdigit() and not re.fullmatch(
            r"[1-5Xx]{3}|default", status_text
        ):
            raise GenerationError(
                f"{method.upper()} {path} has invalid response status {status_text!r}"
            )
        responses.append(
            Response(
                status=status,
                annotation=annotation,
                model_annotation=model_annotation,
                success=success,
                kind=kind,
                media_type=media_type,
                contents=contents,
                headers=headers,
                result_annotation=(
                    f"{class_name(operation_name)}Result{status_text.upper()}"
                    if headers
                    else None
                ),
            )
        )
    if not any(response.success for response in responses):
        raise GenerationError(f"{method.upper()} {path} has no 2xx response")
    return tuple(sorted(responses, key=_response_sort_key))


def _read_response_headers(
    values: Mapping[str, Reference | APIHeader],
    spec: OpenAPISpec,
    method: HttpMethod,
    path: str,
) -> tuple[ResponseHeader, ...]:
    headers: list[ResponseHeader] = []
    for wire_name, raw_header in values.items():
        header = raw_header
        if isinstance(header, Reference):
            header = APIHeader.model_validate(
                _resolve_component(header.ref, "headers", spec.components.headers)
            )
        if header.content:
            raise GenerationError(
                f"{method.upper()} {path} response header {wire_name!r} uses "
                "unsupported content encoding"
            )
        if is_object(header.schema_):
            raise GenerationError(
                f"{method.upper()} {path} response header {wire_name!r} has an "
                "unsupported object schema"
            )
        headers.append(
            ResponseHeader(
                name=_header_identifier(wire_name),
                wire_name=wire_name,
                annotation=schema_type(header.schema_),
            )
        )
    names = [header.name for header in headers]
    if "body" in names or len(names) != len(set(names)):
        raise GenerationError(
            f"{method.upper()} {path} has response header names that collide in Python"
        )
    return tuple(headers)


def _header_identifier(value: str) -> str:
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    return identifier(separated.lower())


def response_model_names(operation: Operation) -> list[str]:
    return [
        response.result_annotation
        for response in operation.responses
        if response.result_annotation is not None
    ]


def _is_success_status(value: str) -> bool:
    return (value.isdigit() and 200 <= int(value) < 300) or value.upper() == "2XX"


def _response_sort_key(response: Response) -> tuple[int, str]:
    if isinstance(response.status, int):
        return 0, f"{response.status:03d}"
    if response.status == "DEFAULT":
        return 2, response.status
    return 1, response.status


def _response_model(
    schema: Mapping[str, Any] | None,
    schemas: Mapping[str, Any],
) -> str | None:
    if not schema or "$ref" not in schema:
        return None
    name = _reference_name(schema["$ref"], "schemas")
    bases, own_schema = split_all_of(schemas.get(name, {}))
    return class_name(name) if bases or is_object(own_schema) else None


def _select_media(
    content: Mapping[str, MediaType], context: str, *, kinds: Sequence[str]
) -> tuple[Mapping[str, Any], str, str]:
    """Pick the one media type a generated method uses, preferring JSON."""
    return _media_options(content, context, kinds=kinds)[0]


def _media_options(
    content: Mapping[str, MediaType], context: str, *, kinds: Sequence[str]
) -> tuple[tuple[Mapping[str, Any], str, str], ...]:
    if not content:
        raise GenerationError(f"{context} has no content types")
    options: list[tuple[Mapping[str, Any], str, str]] = []
    unsupported: list[str] = []
    for media_type, media in content.items():
        kind = _media_kind(media_type, media)
        schema = _media_schema(media, kind)
        if kind not in kinds or schema is None:
            unsupported.append(media_type)
        else:
            options.append((schema, media_type, kind))
    if unsupported:
        raise GenerationError(
            f"unsupported {context} media type(s): {', '.join(unsupported)}"
        )
    return tuple(sorted(options, key=lambda item: item[2] != "json"))


def _media_kind(media_type: str, media: MediaType) -> str:
    normalized = media_type.split(";", 1)[0].strip().lower()
    if normalized == "application/json" or normalized.endswith("+json"):
        return "json"
    if normalized == "application/x-www-form-urlencoded":
        return "form"
    if normalized == "multipart/form-data":
        return "multipart"
    if normalized.startswith("text/"):
        return "text"
    if (
        normalized == "application/octet-stream"
        or (media.schema_ or {}).get("format") == "binary"
    ):
        return "binary"
    return "unsupported"


def _media_schema(media: MediaType, kind: str) -> Mapping[str, Any]:
    if media.schema_:
        return media.schema_
    if kind == "text":
        return {"type": "string"}
    if kind == "binary":
        return {"type": "string", "format": "binary"}
    return {}


def _content_annotation(schema: Mapping[str, Any], kind: str) -> str:
    if kind == "binary":
        return "bytes"
    if kind == "text":
        return "str"
    return schema_type(schema)


def _resolve_component(
    reference: str, section: str, values: Mapping[str, dict[str, Any]]
) -> dict[str, Any]:
    name = _reference_name(reference, section)
    try:
        return values[name]
    except KeyError as error:
        raise GenerationError(f"unresolved reference: {reference}") from error


def _reference_name(reference: str, section: str) -> str:
    prefix = f"#/components/{section}/"
    if not reference.startswith(prefix):
        raise GenerationError(
            f"only local component references are supported: {reference}"
        )
    return reference.removeprefix(prefix).replace("~1", "/").replace("~0", "~")


def read_security_schemes(spec: OpenAPISpec) -> tuple[SecurityScheme, ...]:
    result: list[SecurityScheme] = []
    for name, raw in spec.components.security_schemes.items():
        kind = raw.get("type")
        if kind == "apiKey":
            location = raw.get("in")
            parameter_name = raw.get("name")
            if location not in {"header", "query", "cookie"} or not parameter_name:
                raise GenerationError(f"invalid apiKey security scheme: {name}")
            result.append(SecurityScheme(name, "apiKey", location, parameter_name))
        elif kind == "http" and raw.get("scheme", "").lower() in {
            "bearer",
            "basic",
        }:
            scheme = raw["scheme"].lower()
            result.append(
                SecurityScheme(
                    name,
                    scheme,
                    "header",
                    "Authorization",
                    scheme.title(),
                )
            )
        elif kind in {"oauth2", "openIdConnect"}:
            result.append(
                SecurityScheme(name, "bearer", "header", "Authorization", "Bearer")
            )
        else:
            raise GenerationError(
                f"unsupported security scheme {name!r} of type {kind!r}"
            )
    return tuple(result)


def _constraints(schema: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    names = {
        "minimum": "ge",
        "maximum": "le",
        "exclusiveMinimum": "gt",
        "exclusiveMaximum": "lt",
        "multipleOf": "multiple_of",
        "minLength": "min_length",
        "maxLength": "max_length",
        "minItems": "min_length",
        "maxItems": "max_length",
        "pattern": "pattern",
    }
    return tuple(
        (target, schema[source])
        for source, target in names.items()
        if source in schema and not isinstance(schema[source], bool)
    )


def _parameter_default_source(
    schema: Mapping[str, Any], spec: OpenAPISpec
) -> str | None:
    if "default" not in schema:
        return None
    default = schema["default"]
    reference = schema.get("$ref")
    if isinstance(reference, str):
        name = _reference_name(reference, "schemas")
        target = spec.components.schemas.get(name, {})
        if isinstance(default, str) and default in target.get("enum", []):
            return f"{class_name(name)}.{enum_member(default)}"
    return repr(default)
