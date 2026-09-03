from copy import deepcopy
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.naming import class_name
from httpxgen.openapi import HttpMethod, OpenAPISpec


def normalize_inline_schemas(spec: OpenAPISpec) -> OpenAPISpec:
    document = spec.model_dump(by_alias=True, exclude_none=True)
    if spec.openapi.startswith("3.0"):
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
    try:
        _validate_references(document)
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
            if "const" not in field and "enum" not in field:
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
