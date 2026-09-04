import pytest

from httpxgen.generator import GenerationError
from httpxgen.generator.operations import NO_DEFAULT, read_operations
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
        (201, "Charge"),
        (400, None),
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
            "unsupported request body",
        ),
        (
            {"operationId": "createCharge", "responses": {"400": {}}},
            "no 2xx response",
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


def test_parameters_override_components_and_response_ranges_are_read():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items/{itemId}": {
                    "parameters": [
                        {"$ref": "#/components/parameters/ItemId"},
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer"},
                        },
                    ],
                    "get": {
                        "operationId": "getItem",
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "schema": {"type": "integer", "default": 20},
                            },
                            {
                                "name": "session",
                                "in": "cookie",
                                "schema": {"type": "string"},
                            },
                        ],
                        "responses": {
                            "2XX": {
                                "content": {
                                    "application/problem+json": {
                                        "schema": {"type": "object"}
                                    }
                                }
                            },
                            "default": {
                                "content": {
                                    "text/plain": {"schema": {"type": "string"}}
                                }
                            },
                        },
                    },
                }
            },
            "components": {
                "parameters": {
                    "ItemId": {
                        "name": "itemId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                }
            },
        }
    )

    operation = read_operations(spec)[0]

    assert [(item.wire_name, item.default) for item in operation.parameters][:2] == [
        ("itemId", NO_DEFAULT),
        ("limit", 20),
    ]
    assert operation.parameters[2].location == "cookie"
    assert [(item.status, item.success, item.kind) for item in operation.responses] == [
        ("2XX", True, "json"),
        ("DEFAULT", False, "text"),
    ]


def test_security_is_inherited_and_can_be_disabled_per_operation():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "security": [{"bearerAuth": []}],
            "paths": {
                "/private": {"get": _empty_operation("private")},
                "/public": {"get": {**_empty_operation("public"), "security": []}},
            },
            "components": {
                "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}
            },
        }
    )

    operations = {item.name: item for item in read_operations(spec)}

    assert operations["private"].security == (("bearerAuth",),)
    assert operations["public"].security == ()


def test_request_body_and_response_component_references_are_resolved():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "post": {
                        "operationId": "createItem",
                        "requestBody": {"$ref": "#/components/requestBodies/Item"},
                        "responses": {
                            "201": {"$ref": "#/components/responses/Created"}
                        },
                    }
                }
            },
            "components": {
                "requestBodies": {
                    "Item": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "string"}}},
                    }
                },
                "responses": {
                    "Created": {
                        "content": {"text/plain": {"schema": {"type": "string"}}}
                    }
                },
            },
        }
    )

    operation = read_operations(spec)[0]

    assert operation.body_annotation == "str"
    assert operation.body_required
    assert operation.responses[0].kind == "text"


@pytest.mark.parametrize(
    ("media_type", "schema", "kind", "annotation", "binary_fields"),
    [
        (
            "application/x-www-form-urlencoded",
            {"type": "object", "properties": {"name": {"type": "string"}}},
            "form",
            "dict[str, Any]",
            (),
        ),
        (
            "multipart/form-data",
            {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
            },
            "multipart",
            "dict[str, Any]",
            ("file",),
        ),
        (
            "application/octet-stream",
            {"type": "string", "format": "binary"},
            "binary",
            "bytes",
            (),
        ),
    ],
)
def test_request_body_encodings_are_read(
    media_type, schema, kind, annotation, binary_fields
):
    spec = _spec_with_operation(
        {
            "operationId": "upload",
            "requestBody": {
                "required": True,
                "content": {media_type: {"schema": schema}},
            },
            "responses": {"204": {}},
        }
    )

    body = read_operations(spec)[0].body

    assert body is not None
    assert (body.kind, body.annotation, body.binary_fields) == (
        kind,
        annotation,
        binary_fields,
    )


def test_multiple_request_and_response_content_types_are_kept():
    spec = _spec_with_operation(
        {
            "operationId": "convert",
            "requestBody": {
                "required": True,
                "content": {
                    "text/plain": {"schema": {"type": "string"}},
                    "application/json": {"schema": {"type": "integer"}},
                },
            },
            "responses": {
                "200": {
                    "content": {
                        "text/plain": {"schema": {"type": "string"}},
                        "application/json": {"schema": {"type": "integer"}},
                    }
                }
            },
        }
    )

    operation = read_operations(spec)[0]

    assert [(body.media_type, body.kind) for body in operation.bodies] == [
        ("application/json", "json"),
        ("text/plain", "text"),
    ]
    assert operation.body_annotation == "int | str"
    assert [content.media_type for content in operation.responses[0].contents] == [
        "application/json",
        "text/plain",
    ]
    assert operation.responses[0].annotation == "int | str"


def test_response_headers_are_typed_and_named_as_a_result_model():
    spec = _spec_with_operation(
        {
            "operationId": "getLimits",
            "responses": {
                "200": {
                    "headers": {
                        "X-Request-ID": {"$ref": "#/components/headers/RequestId"},
                        "X-Remaining": {"schema": {"type": "integer"}},
                        "X-RateLimit-Reset": {"schema": {"type": "integer"}},
                    },
                    "content": {"application/json": {"schema": {"type": "string"}}},
                }
            },
        }
    )
    spec.components.headers["RequestId"] = {
        "schema": {"type": "string", "format": "uuid"}
    }

    response = read_operations(spec)[0].responses[0]

    assert response.result_annotation == "GetLimitsResult200"
    assert [
        (header.name, header.wire_name, header.annotation)
        for header in response.headers
    ] == [
        ("x_request_id", "X-Request-ID", "UUID"),
        ("x_remaining", "X-Remaining", "int"),
        ("x_rate_limit_reset", "X-RateLimit-Reset", "int"),
    ]


def test_referenced_enum_defaults_use_enum_members():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "get": {
                        "operationId": "listItems",
                        "parameters": [
                            {
                                "name": "state",
                                "in": "query",
                                "schema": {
                                    "$ref": "#/components/schemas/State",
                                    "default": "open",
                                },
                            }
                        ],
                        "responses": {"204": {}},
                    }
                }
            },
            "components": {
                "schemas": {"State": {"type": "string", "enum": ["open", "closed"]}}
            },
        }
    )

    parameter = read_operations(spec)[0].parameters[0]

    assert parameter.default_source == "State.OPEN"


def _spec_with_operation(
    operation,
    *,
    path_parameters=(),
    schemas=None,
):
    path = "/accounts/{accountId}/charges" if path_parameters else "/charges"
    return OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                path: {
                    "parameters": path_parameters,
                    "post": operation,
                }
            },
            "components": {"schemas": schemas or {}},
        }
    )


def _empty_operation(operation_id):
    return {"operationId": operation_id, "responses": {"204": {}}}
