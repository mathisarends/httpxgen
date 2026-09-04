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


def test_directional_models_are_applied_through_reusable_content_components():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/users": {
                    "post": {
                        "operationId": "createUser",
                        "requestBody": {"$ref": "#/components/requestBodies/User"},
                        "responses": {"201": {"$ref": "#/components/responses/User"}},
                    }
                }
            },
            "components": {
                "schemas": {
                    "User": {
                        "type": "object",
                        "required": ["id", "password"],
                        "properties": {
                            "id": {"type": "string", "readOnly": True},
                            "password": {"type": "string", "writeOnly": True},
                        },
                    }
                },
                "requestBodies": {
                    "User": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        }
                    }
                },
                "responses": {
                    "User": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        }
                    }
                },
            },
        }
    )

    normalized = normalize_inline_schemas(spec)
    request_schema = normalized.components.request_bodies["User"]["content"][
        "application/json"
    ]["schema"]
    response_schema = normalized.components.responses["User"]["content"][
        "application/json"
    ]["schema"]

    assert request_schema == {"$ref": "#/components/schemas/UserRequest"}
    assert response_schema == {"$ref": "#/components/schemas/UserResponse"}
    assert normalized.components.schemas["UserRequest"]["required"] == ["password"]
    assert normalized.components.schemas["UserResponse"]["required"] == ["id"]


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

    with pytest.raises(
        GenerationError,
        match=r"Combined.*value.*A \('string'\).*B \('integer'\)",
    ):
        normalize_inline_schemas(spec)


def test_conflicting_all_of_property_constraints_are_rejected():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {},
            "components": {
                "schemas": {
                    "ShortName": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "maxLength": 20}},
                    },
                    "LongName": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "maxLength": 100}},
                    },
                    "Combined": {
                        "allOf": [
                            {"$ref": "#/components/schemas/ShortName"},
                            {"$ref": "#/components/schemas/LongName"},
                        ]
                    },
                }
            },
        }
    )

    with pytest.raises(GenerationError, match=r"Combined.*name.*ShortName.*LongName"):
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


def test_single_reference_all_of_collapses_to_reference_siblings():
    def make(version):
        return OpenAPISpec.model_validate(
            {
                "openapi": version,
                "paths": {},
                "components": {
                    "schemas": {
                        "Status": {"type": "string", "enum": ["open", "closed"]},
                        "Item": {
                            "type": "object",
                            "properties": {
                                "status": {
                                    "allOf": [{"$ref": "#/components/schemas/Status"}],
                                    "default": "open",
                                }
                            },
                        },
                    }
                },
            }
        )

    expected = {"$ref": "#/components/schemas/Status", "default": "open"}
    for version in ("3.0.3", "3.1.0"):
        schemas = normalize_inline_schemas(make(version)).components.schemas
        assert schemas["Item"]["properties"]["status"] == expected


def test_all_of_with_structure_is_left_as_composition():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {},
            "components": {
                "schemas": {
                    "Base": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                    },
                    "Item": {
                        "allOf": [{"$ref": "#/components/schemas/Base"}],
                        "required": ["name"],
                        "properties": {"name": {"type": "string"}},
                    },
                }
            },
        }
    )

    item = normalize_inline_schemas(spec).components.schemas["Item"]

    assert item["allOf"] == [{"$ref": "#/components/schemas/Base"}]
    assert "$ref" not in item


def _schemas_spec(schemas):
    return OpenAPISpec.model_validate(
        {"openapi": "3.1.0", "paths": {}, "components": {"schemas": schemas}}
    )


_VARIANTS = {
    "Cat": {"type": "object", "properties": {"kind": {"type": "string"}}},
    "Dog": {"type": "object", "properties": {"kind": {"type": "string"}}},
}


@pytest.mark.parametrize(
    ("discriminator", "variants", "message"),
    [
        (
            {"propertyName": "kind"},
            None,
            "discriminator requires oneOf or anyOf",
        ),
        ({}, "oneOf", "discriminator has no propertyName"),
        (
            {"propertyName": "kind", "mapping": {"c": "Missing"}},
            "oneOf",
            "points at unknown schema",
        ),
        (
            {"propertyName": "kind", "mapping": {"d": "Dog"}},
            "oneOf",
            "which is not one of the variants",
        ),
    ],
)
def test_invalid_discriminators_are_rejected(discriminator, variants, message):
    union = {"discriminator": discriminator}
    if variants is None:
        union["allOf"] = [{"$ref": "#/components/schemas/Cat"}]
    else:
        union[variants] = [{"$ref": "#/components/schemas/Cat"}]

    with pytest.raises(GenerationError) as error:
        normalize_inline_schemas(_schemas_spec({**_VARIANTS, "Pet": union}))

    assert message in str(error.value)


def test_discriminated_union_variants_must_be_references():
    union = {
        "oneOf": [{"type": "object", "properties": {"kind": {"type": "string"}}}],
        "discriminator": {"propertyName": "kind"},
    }

    with pytest.raises(GenerationError) as error:
        normalize_inline_schemas(_schemas_spec({**_VARIANTS, "Pet": union}))

    assert "must be a $ref" in str(error.value)


def test_discriminator_mapping_accepts_bare_schema_names():
    union = {
        "oneOf": [
            {"$ref": "#/components/schemas/Cat"},
            {"$ref": "#/components/schemas/Dog"},
        ],
        "discriminator": {
            "propertyName": "kind",
            "mapping": {"cat": "Cat", "dog": "Dog"},
        },
    }

    schemas = normalize_inline_schemas(
        _schemas_spec({**_VARIANTS, "Pet": union})
    ).components.schemas

    assert schemas["Cat"]["properties"]["kind"]["const"] == "cat"
    assert schemas["Dog"]["properties"]["kind"]["const"] == "dog"


def test_required_property_may_not_also_declare_a_default():
    schemas = {
        "Item": {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string", "default": "x"}},
        }
    }

    with pytest.raises(GenerationError) as error:
        normalize_inline_schemas(_schemas_spec(schemas))

    assert "required and also declares a default" in str(error.value)


def test_optional_property_defaults_stay_valid():
    schemas = {
        "Item": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "retries": {"type": "integer", "default": 3},
            },
        }
    }

    item = normalize_inline_schemas(_schemas_spec(schemas)).components.schemas["Item"]

    assert item["properties"]["retries"]["default"] == 3
