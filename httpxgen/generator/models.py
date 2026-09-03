from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.naming import (
    class_name,
    enum_member,
    field_identifier,
    string_literal,
    used_names,
)
from httpxgen.generator.operations import (
    NO_DEFAULT,
    Operation,
    Parameter,
    query_model_name,
    query_parameters,
)
from httpxgen.generator.schema import (
    is_object,
    ordered_schemas,
    schema_type,
    split_all_of,
)
from httpxgen.generator.templates import TemplateName, render_template

_MISSING = object()


@dataclass(frozen=True)
class _DiscriminatorEnum:
    name: str
    values: tuple[str, ...]


def render_models(
    schemas: Mapping[str, Any],
    operations: Sequence[Operation] = (),
) -> str:
    query_names = [
        query_model_name(operation)
        for operation in operations
        if query_parameters(operation)
    ]
    component_names = [class_name(name) for name in schemas]
    conflicts = sorted(set(query_names).intersection(component_names))
    if conflicts:
        raise GenerationError(
            f"generated query model names conflict with components: {', '.join(conflicts)}"
        )
    discriminator_enums_by_field = _discriminator_enums(schemas)
    blocks = [
        *(
            _render_discriminator_enum(enum)
            for enum in dict.fromkeys(discriminator_enums_by_field.values())
        ),
        *(
            _render_component(name, schemas[name], discriminator_enums_by_field)
            for name in ordered_schemas(schemas)
        ),
        *(
            _render_query_model(operation)
            for operation in operations
            if query_parameters(operation)
        ),
    ]
    body = "\n\n\n".join(block for block in blocks if block)
    if not body:
        body = "# This API does not define component schemas."
    imports = _render_model_imports(body)
    return render_template(TemplateName.MODELS, imports=imports, body=body)


def exported_model_names(schemas: Mapping[str, Any]) -> list[str]:
    discriminator_names = [
        enum.name for enum in dict.fromkeys(_discriminator_enums(schemas).values())
    ]
    return [
        *discriminator_names,
        *(class_name(name) for name in ordered_schemas(schemas)),
    ]


def _render_query_model(operation: Operation) -> str:
    fields = "\n".join(
        f"    {_render_query_field(parameter)}"
        for parameter in query_parameters(operation)
    )
    return f"class {query_model_name(operation)}(BaseModel):\n{fields}"


def _render_query_field(parameter: Parameter) -> str:
    has_default = parameter.default is not NO_DEFAULT
    default_source = (
        repr(parameter.default)
        if has_default
        else None
        if parameter.required
        else "None"
    )
    arguments = [f"{name}={value!r}" for name, value in parameter.constraints]
    if parameter.name != parameter.wire_name:
        arguments.append(f"serialization_alias={string_literal(parameter.wire_name)}")
    if not arguments:
        suffix = "" if default_source is None else f" = {default_source}"
        return f"{parameter.name}: {parameter.annotation}{suffix}"
    if default_source is not None:
        arguments.insert(0, default_source)
    return f"{parameter.name}: {parameter.annotation} = Field({', '.join(arguments)})"


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


def _discriminator_enums(
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
    names = [enum_member(value) for value in enum.values]
    if len(names) != len(set(names)):
        raise GenerationError(f"{enum.name}: discriminator values collide in Python")
    members = "\n".join(
        f"    {enum_member(value)} = {string_literal(value)}" for value in enum.values
    )
    return render_template(TemplateName.ENUM, name=enum.name, members=members).rstrip(
        "\n"
    )


def _discriminator_annotation(
    schema: Mapping[str, Any], enum: _DiscriminatorEnum
) -> str:
    values = [schema["const"]] if "const" in schema else schema.get("enum", [])
    member_names = [f"{enum.name}.{enum_member(value)}" for value in values]
    members = ", ".join(member_names)
    if len(member_names) == 1:
        return f"Literal[{members}]"
    if len(f"        {members}") <= 88:
        return f"Literal[\n        {members}\n    ]"
    rendered_members = "\n".join(f"        {member}," for member in member_names)
    return f"Literal[\n{rendered_members}\n    ]"


def _default_source(value: Any, enum: _DiscriminatorEnum | None) -> str:
    if enum is not None and isinstance(value, str) and value in enum.values:
        return f"{enum.name}.{enum_member(value)}"
    if isinstance(value, str):
        return string_literal(value)
    return repr(value)


def _render_component(
    name: str,
    schema: Mapping[str, Any],
    discriminator_enums_by_field: Mapping[tuple[str, str], _DiscriminatorEnum],
) -> str:
    component_class_name = class_name(name)
    enum = schema.get("enum")
    if enum is not None and all(isinstance(value, str) for value in enum):
        member_names = [enum_member(value) for value in enum]
        if len(member_names) != len(set(member_names)):
            raise GenerationError(f"{name}: enum values collide as Python names")
        members = "\n".join(
            f"    {enum_member(value)} = {string_literal(value)}" for value in enum
        )
        return render_template(
            TemplateName.ENUM,
            name=component_class_name,
            members=members or "    pass",
        ).rstrip("\n")
    if enum is not None:
        return f"{component_class_name} = {schema_type(schema)}"

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
    if not is_object(own_schema) and not bases:
        return f"{component_class_name} = {schema_type(own_schema)}"

    base = ", ".join(bases) if bases else "BaseModel"
    properties = own_schema.get("properties", {})
    required = set(own_schema.get("required", []))
    field_names = [field_identifier(item) for item in properties]
    if len(field_names) != len(set(field_names)):
        raise GenerationError(f"{name}: property names collide in Python")
    fields = [
        _render_field(
            field_name=field_identifier(wire_name),
            wire_name=wire_name,
            required=wire_name in required,
            schema=field_schema,
            discriminator_enum=discriminator_enums_by_field.get((name, wire_name)),
        )
        for wire_name, field_schema in properties.items()
    ]
    additional = own_schema.get("additionalProperties")
    if isinstance(additional, Mapping):
        fields.append(
            "__pydantic_extra__: dict[str, "
            f"{schema_type(additional)}] = Field(init=False)"
        )
    return render_template(
        TemplateName.MODEL,
        name=component_class_name,
        base=base,
        extra_mode=(
            "forbid" if own_schema.get("additionalProperties") is False else "allow"
        ),
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
    field_args: list[str] = []
    if field_name != wire_name:
        field_args.append(f"alias={string_literal(wire_name)}")
    constraints = {
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
    for openapi_name, pydantic_name in constraints.items():
        if openapi_name in schema and not isinstance(schema[openapi_name], bool):
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
