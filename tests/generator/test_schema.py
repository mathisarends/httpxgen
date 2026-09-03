import pytest

from httpxgen.generator import GenerationError
from httpxgen.generator.schema import (
    allows_none,
    is_object,
    ordered_schemas,
    schema_type,
    split_all_of,
)


@pytest.mark.parametrize(
    ("schema", "annotation"),
    [
        ({"$ref": "#/components/schemas/PaymentMethod"}, "PaymentMethod"),
        ({"type": "array", "items": {"type": "integer"}}, "list[int]"),
        ({"type": ["string", "null"]}, "str | None"),
        ({"type": "string", "format": "date-time"}, "datetime"),
        ({"type": "string", "format": "uuid"}, "UUID"),
        ({"const": "card"}, 'Literal["card"]'),
        ({"enum": ["open", "closed"]}, 'Literal["open", "closed"]'),
        (
            {"oneOf": [{"type": "string"}, {"type": "integer"}]},
            "str | int",
        ),
        (
            {"type": "object", "additionalProperties": {"type": "boolean"}},
            "dict[str, bool]",
        ),
    ],
)
def test_schema_type_translates_openapi_schemas(schema, annotation):
    assert schema_type(schema) == annotation


def test_split_all_of_separates_a_base_from_owned_fields():
    bases, own_schema = split_all_of(
        {
            "allOf": [
                {"$ref": "#/components/schemas/BaseEntity"},
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
            ]
        }
    )

    assert bases == ["BaseEntity"]
    assert own_schema == {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }


def test_split_all_of_rejects_multiple_base_models():
    with pytest.raises(GenerationError, match="multiple inheritance"):
        split_all_of(
            {
                "allOf": [
                    {"$ref": "#/components/schemas/First"},
                    {"$ref": "#/components/schemas/Second"},
                ]
            }
        )


def test_ordered_schemas_places_dependencies_first_and_tolerates_cycles():
    schemas = {
        "Charge": {"$ref": "#/components/schemas/PaymentMethod"},
        "PaymentMethod": {"$ref": "#/components/schemas/Charge"},
        "Receipt": {"$ref": "#/components/schemas/Charge"},
    }

    ordered = ordered_schemas(schemas)

    assert set(ordered) == set(schemas)
    assert ordered.index("Charge") < ordered.index("Receipt")


def test_schema_shape_predicates_recognize_objects_and_nullable_unions():
    assert is_object({"properties": {}})
    assert not is_object({"type": "string"})
    assert allows_none({"anyOf": [{"type": "string"}, {"type": "null"}]})
    assert not allows_none({"type": "string"})
