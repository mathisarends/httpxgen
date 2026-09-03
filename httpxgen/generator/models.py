import json
import keyword
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.templates import TemplateName, render_template

_MISSING = object()


@dataclass(frozen=True)
class _DiscriminatorEnum:
    name: str
    values: tuple[str, ...]


def schema_type(schema: Mapping[str, Any]) -> str:
    """Translate an OpenAPI schema fragment into a Python annotation."""
    if "$ref" in schema:
        return class_name(schema["$ref"].rsplit("/", 1)[-1])

    variants = schema.get("oneOf") or schema.get("anyOf")
    if variants:
        result = " | ".join(schema_type(item) for item in variants)
        return f"({result})"

    if "const" in schema:
        return f"Literal[{_literal_source(schema['const'])}]"

    enum = schema.get("enum")
    if enum is not None:
        return "Literal[" + ", ".join(_literal_source(value) for value in enum) + "]"

    raw_type = schema.get("type")
    nullable = schema.get("nullable") is True
    if isinstance(raw_type, list):
        nullable = nullable or "null" in raw_type
        raw_type = next((item for item in raw_type if item != "null"), None)

    annotation = _primitive_or_collection_type(raw_type, schema)
    if nullable and annotation != "None":
        return f"{annotation} | None"
    return annotation


def to_identifier(value: str) -> str:
    value = re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()
    value = re.sub(r"\W", "_", value)
    if not value or value[0].isdigit():
        value = f"value_{value}"
    if keyword.iskeyword(value):
        value += "_"
    return value


def generate_models(schemas: Mapping[str, Any]) -> str:
    discriminator_enums_by_field = discriminator_enums(schemas)
    blocks = [
        *(
            _render_discriminator_enum(enum)
            for enum in dict.fromkeys(discriminator_enums_by_field.values())
        ),
        *(
            _render_component(name, schemas[name], discriminator_enums_by_field)
            for name in ordered_schemas(schemas)
        ),
    ]
    body = "\n\n\n".join(block for block in blocks if block)
    if not body:
        body = "# This API does not define component schemas."
    imports = _render_model_imports(body)
    return render_template(TemplateName.MODELS, imports=imports, body=body)


def _render_model_imports(body: str) -> str:
    lines: list[str] = []
    datetime_names = used_names(body, ("date", "datetime"))
    typing_names = used_names(body, ("Annotated", "Any", "Literal"))
    pydantic_names = used_names(body, ("BaseModel", "ConfigDict", "Field"))
    if datetime_names:
        lines.append(f"from datetime import {', '.join(datetime_names)}")
    if "StrEnum" in body:
        lines.append("from enum import StrEnum")
    if typing_names:
        lines.append(f"from typing import {', '.join(typing_names)}")
    if "UUID" in body:
        lines.append("from uuid import UUID")
    if pydantic_names:
        if lines:
            lines.append("")
        lines.append(f"from pydantic import {', '.join(pydantic_names)}")
    return "\n".join(lines)


def used_names(source: str, candidates: Sequence[str]) -> list[str]:
    return [name for name in candidates if re.search(rf"\b{re.escape(name)}\b", source)]


def discriminator_enums(
    schemas: Mapping[str, Any],
) -> dict[tuple[str, str], _DiscriminatorEnum]:
    result: dict[tuple[str, str], _DiscriminatorEnum] = {}
    for union_name, union_schema in schemas.items():
        variants = union_schema.get("oneOf") or union_schema.get("anyOf")
        property_name = union_schema.get("discriminator", {}).get("propertyName")
        if not variants or not property_name:
            continue

        enum = _DiscriminatorEnum(
            name=f"{class_name(union_name)}{class_name(property_name)}",
            values=tuple(
                dict.fromkeys(
                    value
                    for variant in variants
                    for value in _discriminator_values(schemas, variant, property_name)
                )
            ),
        )
        if not enum.values:
            continue
        for variant in variants:
            reference = variant.get("$ref")
            if not isinstance(reference, str):
                continue
            component_name = reference.rsplit("/", 1)[-1]
            if _discriminator_values(schemas, variant, property_name):
                result[(component_name, property_name)] = enum
    return result


def _discriminator_values(
    schemas: Mapping[str, Any], variant: Mapping[str, Any], property_name: str
) -> tuple[str, ...]:
    reference = variant.get("$ref")
    if not isinstance(reference, str):
        return ()
    component = schemas.get(reference.rsplit("/", 1)[-1], {})
    _, own_schema = split_all_of(component)
    field_schema = own_schema.get("properties", {}).get(property_name, {})
    values = (
        [field_schema["const"]]
        if "const" in field_schema
        else field_schema.get("enum", [])
    )
    return tuple(value for value in values if isinstance(value, str))


def _render_discriminator_enum(enum: _DiscriminatorEnum) -> str:
    members = "\n".join(
        f"    {_enum_member(value)} = {string_literal(value)}" for value in enum.values
    )
    return render_template(TemplateName.ENUM, name=enum.name, members=members).rstrip(
        "\n"
    )


def _discriminator_annotation(
    schema: Mapping[str, Any], enum: _DiscriminatorEnum
) -> str:
    values = [schema["const"]] if "const" in schema else schema.get("enum", [])
    member_names = [f"{enum.name}.{_enum_member(value)}" for value in values]
    members = ", ".join(member_names)
    if len(member_names) == 1:
        return f"Literal[{members}]"
    if len(f"        {members}") <= 88:
        return f"Literal[\n        {members}\n    ]"
    rendered_members = "\n".join(f"        {member}," for member in member_names)
    return f"Literal[\n{rendered_members}\n    ]"


def _default_source(value: Any, enum: _DiscriminatorEnum | None) -> str:
    if enum is not None and isinstance(value, str) and value in enum.values:
        return f"{enum.name}.{_enum_member(value)}"
    if isinstance(value, str):
        return string_literal(value)
    return repr(value)


def string_literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _literal_source(value: Any) -> str:
    return string_literal(value) if isinstance(value, str) else repr(value)


def _render_component(
    name: str,
    schema: Mapping[str, Any],
    discriminator_enums_by_field: Mapping[tuple[str, str], _DiscriminatorEnum],
) -> str:
    component_class_name = class_name(name)
    enum = schema.get("enum")
    if enum is not None:
        if not all(isinstance(value, str) for value in enum):
            raise GenerationError(f"{name}: only string component enums are supported")
        members = "\n".join(
            f"    {_enum_member(value)} = {string_literal(value)}" for value in enum
        )
        return render_template(
            TemplateName.ENUM,
            name=component_class_name,
            members=members or "    pass",
        ).rstrip("\n")

    variants = schema.get("oneOf") or schema.get("anyOf")
    if variants:
        union = " | ".join(schema_type(item) for item in variants)
        discriminator = schema.get("discriminator", {}).get("propertyName")
        if discriminator:
            rendered = (
                f"{component_class_name} = Annotated[{union}, "
                f"Field(discriminator={string_literal(discriminator)})]"
            )
            if len(rendered) <= 88:
                return rendered
            rendered_union = (
                union
                if len(f"    {union},") <= 88
                else union.replace(" | ", "\n    | ")
            )
            return (
                f"{component_class_name} = Annotated[\n"
                f"    {rendered_union},\n"
                f"    Field(discriminator={string_literal(discriminator)}),\n"
                "]"
            )
        return f"{component_class_name} = {union}"

    bases, own_schema = split_all_of(schema)
    if not is_object_schema(own_schema) and not bases:
        return f"{component_class_name} = {schema_type(own_schema)}"

    base = bases[0] if bases else "BaseModel"
    properties = own_schema.get("properties", {})
    required = set(own_schema.get("required", []))
    fields = [
        _render_field(
            field_name=to_identifier(wire_name),
            wire_name=wire_name,
            required=wire_name in required,
            schema=field_schema,
            discriminator_enum=discriminator_enums_by_field.get((name, wire_name)),
        )
        for wire_name, field_schema in properties.items()
    ]
    return render_template(
        TemplateName.MODEL,
        name=component_class_name,
        base=base,
        forbid_extra=own_schema.get("additionalProperties") is False,
        fields=fields,
    ).rstrip("\n")


def _render_field(
    *,
    field_name: str,
    wire_name: str,
    required: bool,
    schema: Mapping[str, Any],
    discriminator_enum: _DiscriminatorEnum | None = None,
) -> str:
    annotation = (
        _discriminator_annotation(schema, discriminator_enum)
        if discriminator_enum
        else schema_type(schema)
    )
    if not required and "default" not in schema and not _allows_none(schema):
        annotation = f"{annotation} | None"

    field_args: list[str] = []
    if field_name != wire_name:
        field_args.append(f"alias={string_literal(wire_name)}")
    constraints = {
        "minimum": "ge",
        "maximum": "le",
        "exclusiveMinimum": "gt",
        "exclusiveMaximum": "lt",
        "minLength": "min_length",
        "maxLength": "max_length",
        "minItems": "min_length",
        "maxItems": "max_length",
        "pattern": "pattern",
    }
    for openapi_name, pydantic_name in constraints.items():
        if openapi_name in schema:
            field_args.append(f"{pydantic_name}={schema[openapi_name]!r}")

    default = schema.get("default", _MISSING)
    if default is not _MISSING:
        default_source = _default_source(default, discriminator_enum)
    elif required:
        default_source = None
    else:
        default_source = "None"
    if not field_args:
        suffix = "" if default_source is None else f" = {default_source}"
        rendered = f"{field_name}: {annotation}{suffix}"
        if len(rendered) + 4 <= 88 or default_source is None:
            return rendered
        if annotation.endswith(" | None"):
            optional_base = annotation.removesuffix(" | None")
            if optional_base.startswith("(") and optional_base.endswith(")"):
                optional_base = optional_base[1:-1]
            return (
                f"{field_name}: (\n"
                f"        {optional_base}\n"
                f"    ) | None = {default_source}"
            )
        return f"{field_name}: {annotation} = (\n        {default_source}\n    )"
    field_arguments = (
        field_args if default_source is None else [default_source, *field_args]
    )
    arguments = ", ".join(field_arguments)
    rendered = f"{field_name}: {annotation} = Field({arguments})"
    if len(rendered) + 4 <= 88:
        return rendered
    return f"{field_name}: {annotation} = Field(\n        {arguments}\n    )"


def split_all_of(
    schema: Mapping[str, Any],
) -> tuple[list[str], Mapping[str, Any]]:
    all_of = schema.get("allOf")
    if not all_of:
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


def _primitive_or_collection_type(raw_type: Any, schema: Mapping[str, Any]) -> str:
    if raw_type == "array":
        return f"list[{schema_type(schema.get('items', {}))}]"
    if raw_type == "object" or "properties" in schema:
        additional = schema.get("additionalProperties")
        value_type = (
            schema_type(additional) if isinstance(additional, Mapping) else "Any"
        )
        return f"dict[str, {value_type}]"
    if raw_type == "integer":
        return "int"
    if raw_type == "number":
        return "float"
    if raw_type == "boolean":
        return "bool"
    if raw_type == "string":
        return {
            "date": "date",
            "date-time": "datetime",
            "uuid": "UUID",
        }.get(schema.get("format"), "str")
    if raw_type == "null":
        return "None"
    return "Any"


def ordered_schemas(schemas: Mapping[str, Any]) -> list[str]:
    """Order dependencies before aliases while remaining stable for model cycles."""
    result: list[str] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in visited or name in visiting:
            return
        visiting.add(name)
        for dependency in sorted(_schema_dependencies(schemas[name])):
            if dependency in schemas:
                visit(dependency)
        visiting.remove(name)
        visited.add(name)
        result.append(name)

    for name in sorted(schemas):
        visit(name)
    return result


def _schema_dependencies(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        dependencies = set()
        reference = value.get("$ref")
        if isinstance(reference, str):
            dependencies.add(reference.rsplit("/", 1)[-1])
        for nested in value.values():
            dependencies.update(_schema_dependencies(nested))
        return dependencies
    if isinstance(value, list):
        dependencies = set()
        for nested in value:
            dependencies.update(_schema_dependencies(nested))
        return dependencies
    return set()


def is_object_schema(schema: Mapping[str, Any]) -> bool:
    return schema.get("type") == "object" or "properties" in schema


def _allows_none(schema: Mapping[str, Any]) -> bool:
    raw_type = schema.get("type")
    return (
        schema.get("nullable") is True
        or (isinstance(raw_type, list) and "null" in raw_type)
        or any(
            _allows_none(variant)
            for variant in (schema.get("oneOf") or schema.get("anyOf") or [])
        )
    )


def class_name(value: str) -> str:
    words = re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+", value)
    result = "".join(word[:1].upper() + word[1:] for word in words) or "Model"
    return f"Model{result}" if result[0].isdigit() else result


def _enum_member(value: str) -> str:
    result = re.sub(r"\W+", "_", value).strip("_").upper() or "EMPTY"
    if result[0].isdigit():
        result = f"VALUE_{result}"
    return result
