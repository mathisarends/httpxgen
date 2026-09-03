import pytest

from httpxgen.generator import GenerationError
from httpxgen.generator.operations import read_operations
from httpxgen.openapi import HttpMethod, OpenAPISpec


def test_read_operations_builds_the_generation_model():
    spec = _spec_with_operation(
        {
            "operationId": "createCharge",
            "parameters": [
                {"name": "trace-id", "in": "header", "schema": {"type": "string"}}
            ],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/CreateCharge"}
                    }
                },
            },
            "responses": {
                "201": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Charge"}
                        }
                    }
                },
                "400": {},
            },
        },
        path_parameters=[
            {"name": "accountId", "in": "path", "schema": {"type": "string"}}
        ],
        schemas={
            "CreateCharge": {"type": "object"},
            "Charge": {"type": "object"},
        },
    )

    operations = read_operations(spec)

    assert len(operations) == 1
    operation = operations[0]
    assert operation.method is HttpMethod.POST
    assert operation.name == "create_charge"
    assert operation.body_annotation == "CreateCharge"
    assert operation.body_required
    assert [(item.name, item.required) for item in operation.parameters] == [
        ("account_id", True),
        ("trace_id", False),
    ]
    assert [(item.status, item.model_annotation) for item in operation.responses] == [
        (201, "Charge")
    ]


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ({"responses": {"204": {}}}, "has no operationId"),
        (
            {
                "operationId": "uploadAvatar",
                "requestBody": {"content": {"image/png": {"schema": {}}}},
                "responses": {"204": {}},
            },
            "application/json",
        ),
        (
            {
                "operationId": "streamCharges",
                "parameters": [{"name": "cursor", "in": "cookie"}],
                "responses": {"204": {}},
            },
            "unsupported parameter location",
        ),
        (
            {"operationId": "createCharge", "responses": {"400": {}}},
            "no explicit 2xx response",
        ),
    ],
)
def test_read_operations_rejects_unsupported_operations(operation, message):
    with pytest.raises(GenerationError, match=message):
        read_operations(_spec_with_operation(operation))


def test_read_operations_rejects_duplicate_python_identifiers():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/first": {"get": _empty_operation("listCharges")},
                "/second": {"get": _empty_operation("list_charges")},
            },
        }
    )

    with pytest.raises(GenerationError, match="unique Python identifiers"):
        read_operations(spec)


def _spec_with_operation(
    operation,
    *,
    path_parameters=(),
    schemas=None,
):
    return OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/accounts/{accountId}/charges": {
                    "parameters": path_parameters,
                    "post": operation,
                }
            },
            "components": {"schemas": schemas or {}},
        }
    )


def _empty_operation(operation_id):
    return {"operationId": operation_id, "responses": {"204": {}}}
