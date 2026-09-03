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
