from copy import deepcopy
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.naming import class_name
from httpxgen.openapi import HttpMethod, OpenAPISpec


def normalize_inline_schemas(spec: OpenAPISpec) -> OpenAPISpec:
    document = spec.model_dump(by_alias=True, exclude_none=True)
    if spec.openapi.startswith("3.0"):
        _strip_oas30_reference_siblings(document)
        _normalize_oas30_keywords(document)
    components = document.setdefault("components", {})
    schemas: dict[str, dict[str, Any]] = components.setdefault("schemas", {})
    if "ApiError" in schemas and "ApiErrorModel" not in schemas:
        schemas["ApiErrorModel"] = schemas.pop("ApiError")
        document = _rewrite_reference(
            document,
            "#/components/schemas/ApiError",
            "#/components/schemas/ApiErrorModel",
        )
        components = document["components"]
        schemas = components["schemas"]
    _normalize_discriminators(schemas)

    def unique_name(suggested: str, schema: dict[str, Any]) -> str:
        base = class_name(suggested)
        candidate = base
        index = 2
        while candidate in schemas and schemas[candidate] != schema:
            candidate = f"{base}{index}"
            index += 1
        return candidate

    def process(schema: Any, suggested: str, *, lift_root: bool) -> Any:
        if not isinstance(schema, dict):
            return schema
        schema = deepcopy(schema)
        properties = schema.get("properties")
        if isinstance(properties, dict):
            schema["properties"] = {
                name: process(value, f"{suggested}{class_name(name)}", lift_root=True)
                for name, value in properties.items()
            }
        if isinstance(schema.get("items"), dict):
            schema["items"] = process(
                schema["items"], f"{suggested}Item", lift_root=True
            )
        for keyword in ("oneOf", "anyOf"):
            if isinstance(schema.get(keyword), list):
                schema[keyword] = [
                    process(value, f"{suggested}Variant{index}", lift_root=True)
                    for index, value in enumerate(schema[keyword], 1)
                ]
        if isinstance(schema.get("allOf"), list):
            schema["allOf"] = [
                process(value, f"{suggested}Part{index}", lift_root=False)
                for index, value in enumerate(schema["allOf"], 1)
            ]
        if isinstance(schema.get("additionalProperties"), dict):
            schema["additionalProperties"] = process(
                schema["additionalProperties"],
                f"{suggested}AdditionalProperty",
                lift_root=False,
            )
        is_object = bool(schema.get("properties"))
        if lift_root and is_object and "$ref" not in schema:
            name = unique_name(suggested, schema)
            schemas[name] = schema
            siblings = {
                key: value
                for key, value in schema.items()
                if key
                in {"nullable", "default", "description", "readOnly", "writeOnly"}
            }
            return {"$ref": f"#/components/schemas/{name}", **siblings}
        return schema

    for name in list(schemas):
        schemas[name] = process(schemas[name], name, lift_root=False)

    for component_name, request_body in components.get("requestBodies", {}).items():
        if "$ref" not in request_body:
            for media in request_body.get("content", {}).values():
                if "schema" in media:
                    media["schema"] = process(
                        media["schema"], f"{component_name}Body", lift_root=True
                    )
    for component_name, response in components.get("responses", {}).items():
        if "$ref" not in response:
            for media in response.get("content", {}).values():
                if "schema" in media:
                    media["schema"] = process(
                        media["schema"], f"{component_name}Response", lift_root=True
                    )

    for path_item in document.get("paths", {}).values():
        for parameter in path_item.get("parameters", []):
            if "schema" in parameter:
                parameter["schema"] = process(
                    parameter["schema"],
                    f"{parameter.get('name', 'Parameter')}Parameter",
                    lift_root=True,
                )
        for method in HttpMethod:
            operation = path_item.get(method.value)
            if not operation:
                continue
            operation_name = class_name(operation.get("operationId", method.value))
            for parameter in operation.get("parameters", []):
                if "schema" in parameter:
                    parameter["schema"] = process(
                        parameter["schema"],
                        f"{operation_name}{class_name(parameter.get('name', 'Parameter'))}Parameter",
                        lift_root=True,
                    )
            request_body = operation.get("requestBody", {})
            if "$ref" not in request_body:
                for media in request_body.get("content", {}).values():
                    if "schema" in media:
                        media["schema"] = process(
                            media["schema"], f"{operation_name}Body", lift_root=True
                        )
            for status, response in operation.get("responses", {}).items():
                if "$ref" in response:
                    continue
                for media in response.get("content", {}).values():
                    if "schema" in media:
                        media["schema"] = process(
                            media["schema"],
                            f"{operation_name}Response{status}",
                            lift_root=True,
                        )
    _split_directional_schemas(document)
    try:
        _validate_references(document)
        _validate_schema_semantics(schemas)
        _validate_all_of_conflicts(schemas)
        return OpenAPISpec.model_validate(document)
    except Exception as error:
        raise GenerationError(f"failed to normalize inline schemas: {error}") from error


def _rewrite_reference(value: Any, old: str, new: str) -> Any:
    if isinstance(value, dict):
        return {key: _rewrite_reference(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_reference(item, old, new) for item in value]
    return new if value == old else value


def _normalize_discriminators(schemas: dict[str, dict[str, Any]]) -> None:
    prefix = "#/components/schemas/"
    for union in list(schemas.values()):
        variants = union.get("oneOf") or union.get("anyOf")
        discriminator = union.get("discriminator", {})
        property_name = discriminator.get("propertyName")
        if not variants or not property_name:
            continue
        mapping = discriminator.get("mapping", {})
        values_by_reference = {reference: value for value, reference in mapping.items()}
        for variant in variants:
            reference = variant.get("$ref") if isinstance(variant, dict) else None
            if not isinstance(reference, str) or not reference.startswith(prefix):
                continue
            component_name = (
                reference.removeprefix(prefix).replace("~1", "/").replace("~0", "~")
            )
            component = schemas.get(component_name)
            if component is None:
                continue
            value = values_by_reference.get(reference, component_name)
            target = component
            if component.get("allOf"):
                inline_parts = [
                    item for item in component["allOf"] if "$ref" not in item
                ]
                if not inline_parts:
                    inline_parts.append({"type": "object", "properties": {}})
                    component["allOf"].append(inline_parts[0])
                target = inline_parts[-1]
            properties = target.setdefault("properties", {})
            field = properties.setdefault(property_name, {"type": "string"})
            declared_values = (
                [field["const"]]
                if "const" in field
                else field.get("enum")
                if "enum" in field
                else None
            )
            if declared_values is not None and value not in declared_values:
                raise GenerationError(
                    f"discriminator value {value!r} conflicts with {component_name}.{property_name}"
                )
            if declared_values is None:
                field["const"] = value
            required = target.setdefault("required", [])
            if property_name not in required:
                required.append(property_name)


def _validate_references(document: dict[str, Any]) -> None:
    components = document.get("components", {})

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str):
                prefix = "#/components/"
                if not reference.startswith(prefix):
                    raise GenerationError(
                        f"only local component references are supported: {reference}"
                    )
                section_and_name = reference.removeprefix(prefix).split("/", 1)
                if len(section_and_name) != 2:
                    raise GenerationError(f"invalid component reference: {reference}")
                section, encoded_name = section_and_name
                name = encoded_name.replace("~1", "/").replace("~0", "~")
                if name not in components.get(section, {}):
                    raise GenerationError(f"unresolved reference: {reference}")
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(document)


def _normalize_oas30_keywords(value: Any) -> None:
    if isinstance(value, dict):
        if isinstance(value.get("exclusiveMinimum"), bool):
            exclusive = value.pop("exclusiveMinimum")
            if exclusive and "minimum" in value:
                value["exclusiveMinimum"] = value.pop("minimum")
        if isinstance(value.get("exclusiveMaximum"), bool):
            exclusive = value.pop("exclusiveMaximum")
            if exclusive and "maximum" in value:
                value["exclusiveMaximum"] = value.pop("maximum")
        for item in value.values():
            _normalize_oas30_keywords(item)
    elif isinstance(value, list):
        for item in value:
            _normalize_oas30_keywords(item)


def _strip_oas30_reference_siblings(value: Any) -> None:
    if isinstance(value, dict):
        if "$ref" in value:
            reference = value["$ref"]
            value.clear()
            value["$ref"] = reference
            return
        for item in value.values():
            _strip_oas30_reference_siblings(item)
    elif isinstance(value, list):
        for item in value:
            _strip_oas30_reference_siblings(item)


def _validate_schema_semantics(schemas: dict[str, dict[str, Any]]) -> None:
    def resolved(schema: dict[str, Any]) -> dict[str, Any]:
        reference = schema.get("$ref")
        if not isinstance(reference, str):
            return schema
        prefix = "#/components/schemas/"
        name = reference.removeprefix(prefix).replace("~1", "/").replace("~0", "~")
        return {
            **schemas[name],
            **{key: item for key, item in schema.items() if key != "$ref"},
        }

    def visit(schema: Any, location: str, seen: frozenset[str] = frozenset()) -> None:
        if not isinstance(schema, dict):
            return
        reference = schema.get("$ref")
        if isinstance(reference, str):
            name = (
                reference.removeprefix("#/components/schemas/")
                .replace("~1", "/")
                .replace("~0", "~")
            )
            if name in seen:
                return
            seen = seen | {name}
        effective = resolved(schema)
        if "default" in effective:
            _validate_default(effective, location)
        properties = effective.get("properties", {})
        if isinstance(properties, dict):
            for name, child in properties.items():
                visit(child, f"{location}.{name}", seen)
        if isinstance(effective.get("items"), dict):
            visit(effective["items"], f"{location}[]", seen)
        for keyword in ("oneOf", "anyOf", "allOf"):
            for index, child in enumerate(effective.get(keyword, []), 1):
                visit(child, f"{location}.{keyword}[{index}]", seen)

    for name, schema in schemas.items():
        visit(schema, name)


def _validate_default(schema: dict[str, Any], location: str) -> None:
    default = schema["default"]
    raw_type = schema.get("type")
    if default is None and (
        schema.get("nullable") is True
        or raw_type == "null"
        or (isinstance(raw_type, list) and "null" in raw_type)
    ):
        return
    if "const" in schema and default != schema["const"]:
        raise GenerationError(f"{location}: default does not match const")
    if "enum" in schema and default not in schema["enum"]:
        raise GenerationError(f"{location}: default is not an enum value")
    allowed = set(raw_type) if isinstance(raw_type, list) else {raw_type}
    checks = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: (
            isinstance(item, (int, float)) and not isinstance(item, bool)
        ),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
        "null": lambda item: item is None,
    }
    typed = {item for item in allowed if item in checks}
    if typed and not any(checks[item](default) for item in typed):
        raise GenerationError(f"{location}: default does not match schema type")


def _validate_all_of_conflicts(schemas: dict[str, dict[str, Any]]) -> None:
    prefix = "#/components/schemas/"

    def properties(schema: dict[str, Any], seen: set[str]) -> dict[str, dict[str, Any]]:
        result = dict(schema.get("properties", {}))
        for item in schema.get("allOf", []):
            reference = item.get("$ref")
            if isinstance(reference, str) and reference.startswith(prefix):
                name = (
                    reference.removeprefix(prefix).replace("~1", "/").replace("~0", "~")
                )
                if name not in seen:
                    result.update(properties(schemas[name], {*seen, name}))
            elif isinstance(item, dict):
                result.update(properties(item, seen))
        return result

    for name, schema in schemas.items():
        sources: dict[str, tuple[dict[str, Any], str]] = {}
        parts = [schema, *schema.get("allOf", [])]
        for index, part in enumerate(parts):
            reference = part.get("$ref") if isinstance(part, dict) else None
            if isinstance(reference, str) and reference.startswith(prefix):
                target = (
                    reference.removeprefix(prefix).replace("~1", "/").replace("~0", "~")
                )
                part_properties = properties(schemas[target], {target})
                source = target
            elif isinstance(part, dict):
                part_properties = part.get("properties", {})
                source = f"inline part {index}"
            else:
                continue
            for property_name, property_schema in part_properties.items():
                semantic_schema = _semantic_schema(property_schema)
                previous = sources.get(property_name)
                if previous is not None and previous[0] != semantic_schema:
                    previous_type = _schema_type_signature(previous[0])
                    current_type = _schema_type_signature(semantic_schema)
                    raise GenerationError(
                        f"{name}: allOf property {property_name!r} conflicts between "
                        f"{previous[1]} ({previous_type}) and {source} "
                        f"({current_type})"
                    )
                sources[property_name] = semantic_schema, source


def _semantic_schema(schema: dict[str, Any]) -> dict[str, Any]:
    annotations = {
        "deprecated",
        "description",
        "example",
        "examples",
        "externalDocs",
        "title",
        "xml",
    }
    return {
        key: (
            _semantic_schema(value)
            if isinstance(value, dict)
            else [
                _semantic_schema(item) if isinstance(item, dict) else item
                for item in value
            ]
            if isinstance(value, list)
            else value
        )
        for key, value in schema.items()
        if key not in annotations
    }


def _schema_type_signature(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"]
    if "type" in schema:
        raw = schema["type"]
        return repr(sorted(raw) if isinstance(raw, list) else raw)
    if "oneOf" in schema:
        return "oneOf"
    if "anyOf" in schema:
        return "anyOf"
    return "unknown"


def _split_directional_schemas(document: dict[str, Any]) -> None:
    components = document.get("components", {})
    schemas: dict[str, dict[str, Any]] = components.get("schemas", {})
    originals = deepcopy(schemas)
    prefix = "#/components/schemas/"
    needs_cache: dict[tuple[str, str], bool] = {}
    variants: dict[tuple[str, str], str] = {}

    def reference_name(reference: str) -> str | None:
        if not reference.startswith(prefix):
            return None
        return reference.removeprefix(prefix).replace("~1", "/").replace("~0", "~")

    def needs_variant(name: str, mode: str, seen: frozenset[str] = frozenset()) -> bool:
        key = name, mode
        if key in needs_cache:
            return needs_cache[key]
        if name in seen or name not in originals:
            return False
        excluded = "readOnly" if mode == "request" else "writeOnly"

        def inspect(value: Any) -> bool:
            if isinstance(value, dict):
                if value.get(excluded) is True:
                    return True
                reference = value.get("$ref")
                target = (
                    reference_name(reference) if isinstance(reference, str) else None
                )
                if target and needs_variant(target, mode, seen | {name}):
                    return True
                return any(inspect(item) for item in value.values())
            if isinstance(value, list):
                return any(inspect(item) for item in value)
            return False

        result = inspect(originals[name])
        needs_cache[key] = result
        return result

    def variant_name(name: str, mode: str) -> str:
        key = name, mode
        if key in variants:
            return variants[key]
        candidate = f"{name}{'Request' if mode == 'request' else 'Response'}"
        if candidate in schemas:
            raise GenerationError(f"directional schema name collision: {candidate}")
        variants[key] = candidate
        schemas[candidate] = {}
        schemas[candidate] = transform(originals[name], mode)
        return candidate

    def transform(value: Any, mode: str) -> Any:
        if isinstance(value, list):
            return [transform(item, mode) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get("$ref")
        target = reference_name(reference) if isinstance(reference, str) else None
        if target and needs_variant(target, mode):
            rewritten = dict(value)
            rewritten["$ref"] = f"{prefix}{variant_name(target, mode)}"
            return rewritten
        result = {key: transform(item, mode) for key, item in value.items()}
        properties = value.get("properties")
        if isinstance(properties, dict):
            excluded = "readOnly" if mode == "request" else "writeOnly"
            kept = {
                name: transform(schema, mode)
                for name, schema in properties.items()
                if schema.get(excluded) is not True
            }
            result["properties"] = kept
            if isinstance(value.get("required"), list):
                result["required"] = [
                    name for name in value["required"] if name in kept
                ]
        discriminator = result.get("discriminator")
        if isinstance(discriminator, dict) and isinstance(
            discriminator.get("mapping"), dict
        ):
            discriminator["mapping"] = {
                key: (
                    f"{prefix}{variant_name(target, mode)}"
                    if (target := reference_name(reference))
                    and needs_variant(target, mode)
                    else reference
                )
                for key, reference in discriminator["mapping"].items()
            }
        return result

    def transform_content(container: dict[str, Any], mode: str) -> None:
        for media in container.get("content", {}).values():
            if "schema" in media:
                media["schema"] = transform(media["schema"], mode)

    for request_body in components.get("requestBodies", {}).values():
        if "$ref" not in request_body:
            transform_content(request_body, "request")
    for response in components.get("responses", {}).values():
        if "$ref" not in response:
            transform_content(response, "response")
    for path_item in document.get("paths", {}).values():
        for method in HttpMethod:
            operation = path_item.get(method.value)
            if not operation:
                continue
            request_body = operation.get("requestBody", {})
            if "$ref" not in request_body:
                transform_content(request_body, "request")
            for response in operation.get("responses", {}).values():
                if "$ref" not in response:
                    transform_content(response, "response")
