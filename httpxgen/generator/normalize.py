from copy import deepcopy
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.naming import class_name
from httpxgen.openapi import HttpMethod, OpenAPISpec


def normalize_inline_schemas(spec: OpenAPISpec) -> OpenAPISpec:
    document = spec.model_dump(by_alias=True, exclude_none=True)
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
                if key in {"nullable", "default", "description", "readOnly", "writeOnly"}
            }
            return {"$ref": f"#/components/schemas/{name}", **siblings}
        return schema

    for name in list(schemas):
        schemas[name] = process(schemas[name], name, lift_root=False)

    for path_item in document.get("paths", {}).values():
        for parameter in path_item.get("parameters", []):
            if "schema" in parameter:
                parameter["schema"] = process(
                    parameter["schema"], f"{parameter.get('name', 'Parameter')}Parameter", lift_root=True
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
        return OpenAPISpec.model_validate(document)
    except Exception as error:
        raise GenerationError(f"failed to normalize inline schemas: {error}") from error


def _rewrite_reference(value: Any, old: str, new: str) -> Any:
    if isinstance(value, dict):
        return {key: _rewrite_reference(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_reference(item, old, new) for item in value]
    return new if value == old else value
