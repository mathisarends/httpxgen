from collections.abc import Mapping
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.naming import class_name, string_literal


def schema_type(schema: Mapping[str, Any]) -> str:
    if "$ref" in schema:
        return class_name(schema["$ref"].rsplit("/", 1)[-1])

    variants = schema.get("oneOf") or schema.get("anyOf")
    if variants:
        return f"({' | '.join(schema_type(item) for item in variants)})"
    if "const" in schema:
        return f"Literal[{_literal(schema['const'])}]"
    if (enum := schema.get("enum")) is not None:
        return "Literal[" + ", ".join(_literal(value) for value in enum) + "]"

    raw_type = schema.get("type")
    nullable = schema.get("nullable") is True
    if isinstance(raw_type, list):
        nullable = nullable or "null" in raw_type
        raw_type = next((item for item in raw_type if item != "null"), None)

    annotation = _plain_type(raw_type, schema)
    return f"{annotation} | None" if nullable and annotation != "None" else annotation


def split_all_of(
    schema: Mapping[str, Any],
) -> tuple[list[str], Mapping[str, Any]]:
    if not (all_of := schema.get("allOf")):
        return [], schema
    bases = [schema_type(item) for item in all_of if "$ref" in item]
    if len(bases) > 1:
        raise GenerationError("multiple inheritance in allOf is not supported")

    merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    for item in (item for item in all_of if "$ref" not in item):
        merged["properties"].update(item.get("properties", {}))
        merged["required"].extend(item.get("required", []))
        if item.get("additionalProperties") is False:
            merged["additionalProperties"] = False
    return bases, merged


def ordered_schemas(schemas: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in visited or name in visiting:
            return
        visiting.add(name)
        for dependency in sorted(_dependencies(schemas[name])):
            if dependency in schemas:
                visit(dependency)
        visiting.remove(name)
        visited.add(name)
        result.append(name)

    for name in sorted(schemas):
        visit(name)
    return result


def is_object(schema: Mapping[str, Any]) -> bool:
    return schema.get("type") == "object" or "properties" in schema


def allows_none(schema: Mapping[str, Any]) -> bool:
    raw_type = schema.get("type")
    return (
        schema.get("nullable") is True
        or (isinstance(raw_type, list) and "null" in raw_type)
        or any(
            allows_none(variant)
            for variant in (schema.get("oneOf") or schema.get("anyOf") or [])
        )
    )


def _plain_type(raw_type: Any, schema: Mapping[str, Any]) -> str:
    if raw_type == "array":
        return f"list[{schema_type(schema.get('items', {}))}]"
    if raw_type == "object" or "properties" in schema:
        additional = schema.get("additionalProperties")
        value_type = (
            schema_type(additional) if isinstance(additional, Mapping) else "Any"
        )
        return f"dict[str, {value_type}]"
    return {
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "null": "None",
    }.get(raw_type, _string_type(schema) if raw_type == "string" else "Any")


def _string_type(schema: Mapping[str, Any]) -> str:
    return {
        "date": "date",
        "date-time": "datetime",
        "uuid": "UUID",
    }.get(schema.get("format"), "str")


def _literal(value: Any) -> str:
    return string_literal(value) if isinstance(value, str) else repr(value)


def _dependencies(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        dependencies = set()
        if isinstance((reference := value.get("$ref")), str):
            dependencies.add(reference.rsplit("/", 1)[-1])
        for nested in value.values():
            dependencies.update(_dependencies(nested))
        return dependencies
    if isinstance(value, list):
        dependencies = set()
        for nested in value:
            dependencies.update(_dependencies(nested))
        return dependencies
    return set()
