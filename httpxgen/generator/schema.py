from collections.abc import Mapping
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.naming import class_name, string_literal


def schema_type(
    schema: Mapping[str, Any],
    schemas: Mapping[str, Any] | None = None,
    *,
    include_constraints: bool = True,
) -> str:
    annotation = _schema_type(schema, schemas)
    arguments = []
    if include_constraints:
        for source, target in _ANNOTATION_CONSTRAINTS.items():
            if source in schema and not isinstance(schema[source], bool):
                arguments.append(f"{target}={schema[source]!r}")
    if arguments:
        return f"Annotated[{annotation}, Field({', '.join(arguments)})]"
    return annotation


_ANNOTATION_CONSTRAINTS = {
    "minimum": "ge",
    "maximum": "le",
    "exclusiveMinimum": "gt",
    "exclusiveMaximum": "lt",
    "multipleOf": "multiple_of",
    "minLength": "min_length",
    "maxLength": "max_length",
    "pattern": "pattern",
    "minItems": "min_length",
    "maxItems": "max_length",
    "minProperties": "min_length",
    "maxProperties": "max_length",
}


def _schema_type(
    schema: Mapping[str, Any], schemas: Mapping[str, Any] | None = None
) -> str:
    if "$ref" in schema:
        annotation = class_name(
            schema["$ref"].rsplit("/", 1)[-1].replace("~1", "/").replace("~0", "~")
        )
        nullable = allows_none(schema) or _reference_allows_none(
            schema, schemas or {}, set()
        )
        return f"{annotation} | None" if nullable else annotation

    variants = schema.get("oneOf") or schema.get("anyOf")
    if variants:
        variant_types = [schema_type(item, schemas) for item in variants]
        annotation = " | ".join(variant_types)
        if "oneOf" in schema and not schema.get("discriminator"):
            adapters = ", ".join(variant_types)
            annotation = f"Annotated[{annotation}, _one_of({adapters})]"
        if schema.get("nullable") is True and "None" not in annotation:
            annotation += " | None"
        return annotation
    if "const" in schema:
        if "enum" in schema and not any(
            _json_equal(schema["const"], item) for item in schema["enum"]
        ):
            raise GenerationError(
                "schema const is excluded by enum; constraints are contradictory"
            )
        return f"Literal[{_literal(schema['const'])}]"
    if (enum := schema.get("enum")) is not None:
        return "Literal[" + ", ".join(_literal(value) for value in enum) + "]"

    raw_type = schema.get("type")
    nullable = schema.get("nullable") is True
    if isinstance(raw_type, list):
        nullable = nullable or "null" in raw_type
        types = [item for item in raw_type if item != "null"]
        annotation = (
            " | ".join(_plain_type(item, schema, schemas) for item in types) or "None"
        )
        return (
            f"{annotation} | None" if nullable and annotation != "None" else annotation
        )

    annotation = _plain_type(raw_type, schema, schemas)
    return f"{annotation} | None" if nullable and annotation != "None" else annotation


def split_all_of(
    schema: Mapping[str, Any],
) -> tuple[list[str], Mapping[str, Any]]:
    if not (all_of := schema.get("allOf")):
        return [], schema
    bases = [schema_type(item) for item in all_of if "$ref" in item]
    merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    for item in [schema, *(item for item in all_of if "$ref" not in item)]:
        merged["properties"].update(item.get("properties", {}))
        merged["required"].extend(item.get("required", []))
        if item.get("additionalProperties") is False:
            merged["additionalProperties"] = False
        elif isinstance(item.get("additionalProperties"), Mapping):
            merged["additionalProperties"] = item["additionalProperties"]
    return bases, merged


def ordered_schemas(schemas: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in visited or name in visiting:
            return
        visiting.add(name)
        for dependency in sorted(schema_dependencies(schemas[name])):
            if dependency in schemas:
                visit(dependency)
        visiting.remove(name)
        visited.add(name)
        result.append(name)

    for name in sorted(schemas):
        visit(name)
    return result


def recursive_schema_names(schemas: Mapping[str, Any]) -> set[str]:
    graph = {
        name: schema_dependencies(schema) & schemas.keys()
        for name, schema in schemas.items()
    }
    recursive = set()
    for name in schemas:
        pending = list(graph[name])
        seen = set()
        while pending:
            dependency = pending.pop()
            if dependency == name:
                recursive.add(name)
                break
            if dependency not in seen:
                seen.add(dependency)
                pending.extend(graph[dependency])
    return recursive


def is_object(schema: Mapping[str, Any]) -> bool:
    return schema.get("type") == "object" or "properties" in schema


def allows_none(schema: Mapping[str, Any]) -> bool:
    raw_type = schema.get("type")
    return (
        schema.get("nullable") is True
        or raw_type == "null"
        or (isinstance(raw_type, list) and "null" in raw_type)
        or any(
            allows_none(variant)
            for variant in (schema.get("oneOf") or schema.get("anyOf") or [])
        )
    )


def _reference_allows_none(
    schema: Mapping[str, Any], schemas: Mapping[str, Any], seen: set[str]
) -> bool:
    reference = schema.get("$ref")
    if not isinstance(reference, str) or reference in seen:
        return False
    seen.add(reference)
    name = reference.rsplit("/", 1)[-1].replace("~1", "/").replace("~0", "~")
    target = schemas.get(name, {})
    return allows_none(target) or _reference_allows_none(target, schemas, seen)


def _plain_type(
    raw_type: Any, schema: Mapping[str, Any], schemas: Mapping[str, Any] | None = None
) -> str:
    if raw_type == "array":
        return f"list[{schema_type(schema.get('items', {}), schemas)}]"
    if raw_type == "object" or "properties" in schema:
        additional = schema.get("additionalProperties")
        value_type = (
            schema_type(additional, schemas)
            if isinstance(additional, Mapping)
            else "Any"
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
        "binary": "bytes",
        "byte": "bytes",
    }.get(schema.get("format"), "str")


def _literal(value: Any) -> str:
    return string_literal(value) if isinstance(value, str) else repr(value)


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def schema_dependencies(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        dependencies = set()
        if isinstance((reference := value.get("$ref")), str):
            dependencies.add(reference.rsplit("/", 1)[-1])
        for nested in value.values():
            dependencies.update(schema_dependencies(nested))
        return dependencies
    if isinstance(value, list):
        dependencies = set()
        for nested in value:
            dependencies.update(schema_dependencies(nested))
        return dependencies
    return set()
