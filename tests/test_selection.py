import pytest

from httpxgen.generator import GenerationError
from httpxgen.openapi import OpenAPISpec
from httpxgen.selection import filter_operations_by_tags


@pytest.fixture
def tagged_spec() -> OpenAPISpec:
    return OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/charges": {
                    "get": {
                        "operationId": "listCharges",
                        "tags": ["charges"],
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/Charge"
                                        }
                                    }
                                }
                            }
                        },
                    }
                },
                "/customers": {
                    "get": {
                        "operationId": "listCustomers",
                        "tags": ["customers"],
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/Customer"
                                        }
                                    }
                                }
                            }
                        },
                    }
                },
            },
            "components": {
                "schemas": {
                    "Charge": {"type": "object"},
                    "Customer": {
                        "type": "object",
                        "properties": {
                            "address": {"$ref": "#/components/schemas/CustomerAddress"}
                        },
                    },
                    "CustomerAddress": {"type": "object"},
                    "Unused": {"type": "object"},
                }
            },
        }
    )


def test_filter_operations_keeps_matching_paths_and_referenced_schemas(tagged_spec):
    selected = filter_operations_by_tags(tagged_spec, ["customers"])

    assert set(selected.paths) == {"/customers"}
    assert set(selected.components.schemas) == {"Customer", "CustomerAddress"}


def test_schema_tags_retain_models_without_their_operations(tagged_spec):
    selected = filter_operations_by_tags(
        tagged_spec,
        ["charges"],
        schema_tags=["customers"],
    )

    assert set(selected.paths) == {"/charges"}
    assert set(selected.components.schemas) == {
        "Charge",
        "Customer",
        "CustomerAddress",
    }


def test_unknown_tags_are_reported_with_available_tags(tagged_spec):
    with pytest.raises(GenerationError, match="missing.*charges, customers"):
        filter_operations_by_tags(tagged_spec, ["missing"])


def test_empty_tag_filter_returns_an_independent_copy(tagged_spec):
    selected = filter_operations_by_tags(tagged_spec, [])

    assert selected == tagged_spec
    assert selected is not tagged_spec
    assert selected.paths["/charges"] is not tagged_spec.paths["/charges"]


def test_unique_schema_titles_become_canonical_names():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/charges": {
                    "get": {
                        "operationId": "listCharges",
                        "tags": ["charges"],
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/generated-name"
                                        }
                                    }
                                }
                            }
                        },
                    }
                }
            },
            "components": {
                "schemas": {
                    "generated-name": {
                        "title": "Charge",
                        "type": "object",
                    }
                }
            },
        }
    )

    selected = filter_operations_by_tags(spec, ["charges"])

    response = selected.paths["/charges"].get.responses["200"]
    assert set(selected.components.schemas) == {"Charge"}
    assert response.content["application/json"].schema_ == {
        "$ref": "#/components/schemas/Charge"
    }
