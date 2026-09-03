import pytest

from httpxgen.generator import GenerationError
from httpxgen.generator.normalize import normalize_inline_schemas
from httpxgen.openapi import OpenAPISpec


def test_normalization_lifts_inline_models_but_keeps_free_dictionaries():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {},
            "components": {
                "schemas": {
                    "Parent": {
                        "type": "object",
                        "properties": {
                            "child": {
                                "type": "object",
                                "properties": {"name": {"type": "string"}},
                            },
                            "labels": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            },
                        },
                    }
                }
            },
        }
    )

    normalized = normalize_inline_schemas(spec)
    properties = normalized.components.schemas["Parent"]["properties"]

    assert properties["child"] == {"$ref": "#/components/schemas/ParentChild"}
    assert properties["labels"]["additionalProperties"] == {"type": "string"}


def test_normalization_translates_openapi_30_exclusive_bounds():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.0.3",
            "paths": {},
            "components": {
                "schemas": {
                    "Score": {
                        "type": "number",
                        "minimum": 0,
                        "exclusiveMinimum": True,
                        "maximum": 1,
                        "exclusiveMaximum": False,
                    }
                }
            },
        }
    )

    schema = normalize_inline_schemas(spec).components.schemas["Score"]

    assert schema["exclusiveMinimum"] == 0
    assert schema["maximum"] == 1
    assert "minimum" not in schema
    assert "exclusiveMaximum" not in schema


def test_reference_siblings_follow_the_openapi_version():
    def make(version):
        return OpenAPISpec.model_validate(
            {
                "openapi": version,
                "paths": {},
                "components": {
                    "schemas": {
                        "Name": {"type": "string"},
                        "Alias": {
                            "$ref": "#/components/schemas/Name",
                            "nullable": True,
                            "description": "sibling",
                        },
                    }
                },
            }
        )

    old = normalize_inline_schemas(make("3.0.3"))
    current = normalize_inline_schemas(make("3.1.0"))

    assert old.components.schemas["Alias"] == {"$ref": "#/components/schemas/Name"}
    assert current.components.schemas["Alias"]["nullable"] is True


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        ({"type": "integer", "default": "wrong"}, "schema type"),
        ({"type": "string", "enum": ["a"], "default": "b"}, "enum value"),
    ],
)
def test_invalid_schema_defaults_are_rejected(schema, message):
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {},
            "components": {"schemas": {"Value": schema}},
        }
    )

    with pytest.raises(GenerationError, match=message):
        normalize_inline_schemas(spec)


def test_conflicting_all_of_property_types_are_rejected():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {},
            "components": {
                "schemas": {
                    "A": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                    },
                    "B": {
                        "type": "object",
                        "properties": {"value": {"type": "integer"}},
                    },
                    "Combined": {
                        "allOf": [
                            {"$ref": "#/components/schemas/A"},
                            {"$ref": "#/components/schemas/B"},
                        ]
                    },
                }
            },
        }
    )

    with pytest.raises(GenerationError, match="Combined.*value.*conflicts"):
        normalize_inline_schemas(spec)


def test_conflicting_discriminator_mapping_is_rejected():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {},
            "components": {
                "schemas": {
                    "Cat": {
                        "type": "object",
                        "required": ["kind"],
                        "properties": {"kind": {"type": "string", "const": "cat"}},
                    },
                    "Pet": {
                        "oneOf": [{"$ref": "#/components/schemas/Cat"}],
                        "discriminator": {
                            "propertyName": "kind",
                            "mapping": {"feline": "#/components/schemas/Cat"},
                        },
                    },
                }
            },
        }
    )

    with pytest.raises(GenerationError, match="discriminator value"):
        normalize_inline_schemas(spec)
