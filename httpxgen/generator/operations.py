import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.naming import class_name, enum_member, identifier
from httpxgen.generator.schema import is_object, schema_type, split_all_of
from httpxgen.openapi import (
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
class Body:
    annotation: str
    required: bool
    media_type: str
    kind: str
    binary_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class Response:
    status: int | str
    annotation: str
    model_annotation: str | None
    success: bool = True
    kind: str = "json"
    media_type: str | None = None


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


def read_operations(spec: OpenAPISpec) -> tuple[Operation, ...]:
    operations: list[Operation] = []
    schemes = _read_security_schemes(spec)
    for path in sorted(spec.paths):
        path_item = _resolve_path_item(spec.paths[path], spec)
        for method in HttpMethod:
            operation = get_operation(path_item, method)
            if operation is None:
                continue
            if not operation.operation_id:
                raise GenerationError(f"{method.upper()} {path} has no operationId")
            body = _read_body(operation.request_body, spec)
            parameters = _read_parameters(
                [*path_item.parameters, *operation.parameters], spec
            )
            _validate_parameters(path, parameters, has_body=body is not None)
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
                    body_annotation=body.annotation if body else None,
                    body_required=body.required if body else False,
                    responses=_read_responses(operation.responses, method, path, spec),
                    body=body,
                    security=requirements,
                    security_schemes=schemes,
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
            schema, _, _ = _select_media(value.content, "parameter")
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
                name=identifier(value.name),
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


def _read_body(value: RequestBody | Reference | None, spec: OpenAPISpec) -> Body | None:
    if value is None:
        return None
    if isinstance(value, Reference):
        value = RequestBody.model_validate(
            _resolve_component(
                value.ref, "requestBodies", spec.components.request_bodies
            )
        )
    schema, media_type, kind = _select_media(value.content, "request body")
    annotation = (
        "bytes"
        if kind == "binary"
        else "str"
        if kind == "text"
        else schema_type(schema)
    )
    body_shape = schema
    if "$ref" in schema:
        referenced_name = _reference_name(schema["$ref"], "schemas")
        body_shape = spec.components.schemas.get(referenced_name, schema)
    _, body_shape = split_all_of(body_shape)
    binary_fields = tuple(
        name
        for name, field in body_shape.get("properties", {}).items()
        if field.get("format") == "binary"
    )
    return Body(annotation, value.required, media_type, kind, binary_fields)


def _read_responses(
    values: Mapping[str, APIResponse | Reference],
    method: HttpMethod,
    path: str,
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
        if response.content:
            schema, media_type, kind = _select_media(response.content, "response")
            annotation = (
                "bytes"
                if kind == "binary"
                else "str"
                if kind == "text"
                else schema_type(schema)
            )
        else:
            schema, media_type, kind, annotation = None, None, "empty", "None"
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
                model_annotation=_response_model(schema, spec.components.schemas),
                success=success,
                kind=kind,
                media_type=media_type,
            )
        )
    if not any(response.success for response in responses):
        raise GenerationError(f"{method.upper()} {path} has no 2xx response")
    return tuple(sorted(responses, key=_response_sort_key))


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
    content: Mapping[str, MediaType], context: str
) -> tuple[Mapping[str, Any], str, str]:
    for media_type, media in content.items():
        normalized = media_type.split(";", 1)[0].strip().lower()
        if normalized == "application/json" or normalized.endswith("+json"):
            return media.schema_ or {}, media_type, "json"
    for media_type, media in content.items():
        normalized = media_type.split(";", 1)[0].strip().lower()
        if normalized == "multipart/form-data":
            return media.schema_ or {}, media_type, "multipart"
        if normalized == "application/x-www-form-urlencoded":
            return media.schema_ or {}, media_type, "form"
        if normalized.startswith("text/"):
            return media.schema_ or {"type": "string"}, media_type, "text"
        if (
            normalized == "application/octet-stream"
            or (media.schema_ or {}).get("format") == "binary"
        ):
            return (
                media.schema_ or {"type": "string", "format": "binary"},
                media_type,
                "binary",
            )
    offered = ", ".join(content) or "(none)"
    raise GenerationError(f"unsupported {context} media type(s): {offered}")


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


def _read_security_schemes(spec: OpenAPISpec) -> tuple[SecurityScheme, ...]:
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
