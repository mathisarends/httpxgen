import asyncio
import importlib
import sys

import httpx

from httpxgen import OpenAPISpec, write_client


def test_generated_client_serializes_parameters_security_and_typed_errors(tmp_path):
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "security": [{"bearerAuth": []}],
            "paths": {
                "/items/{itemId}": {
                    "get": {
                        "operationId": "getItem",
                        "parameters": [
                            {
                                "name": "itemId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "tag",
                                "in": "query",
                                "schema": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            {
                                "name": "filter",
                                "in": "query",
                                "style": "deepObject",
                                "schema": {
                                    "type": "object",
                                    "properties": {"state": {"type": "string"}},
                                },
                            },
                        ],
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["id"],
                                            "properties": {"id": {"type": "string"}},
                                        }
                                    }
                                }
                            },
                            "404": {
                                "content": {
                                    "application/problem+json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["message"],
                                            "properties": {
                                                "message": {"type": "string"}
                                            },
                                        }
                                    }
                                }
                            },
                        },
                    }
                }
            },
            "components": {
                "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}
            },
        }
    )
    package_dir = tmp_path / "ordinary_api"
    write_client(spec=spec, package_dir=package_dir, package_name="ordinary_api")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.path == "/items/a/b"
        assert request.url.raw_path.startswith(b"/items/a%2Fb")
        assert request.url.params.get_list("tag") == ["one", "two"]
        assert request.url.params["filter[state]"] == "active"
        assert request.headers["Authorization"] == "Bearer secret"
        if len(seen) == 1:
            return httpx.Response(200, json={"id": "a/b", "new_field": 1})
        return httpx.Response(404, json={"message": "gone"})

    sys.path.insert(0, str(tmp_path))
    try:
        package = importlib.import_module("ordinary_api")
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = package.OrdinaryApiClient(
            http_client,
            "https://example.test",
            credentials={"bearerAuth": "secret"},
        )

        async def exercise():
            item = await client.get_item(
                "a/b", tag=["one", "two"], filter={"state": "active"}
            )
            assert item.id == "a/b"
            assert item.new_field == 1
            try:
                await client.get_item(
                    "a/b", tag=["one", "two"], filter={"state": "active"}
                )
            except package.ApiError as error:
                assert error.status_code == 404
                assert error.parsed_body.message == "gone"
            else:
                raise AssertionError("expected ApiError")
            await client.aclose()

        asyncio.run(exercise())
    finally:
        sys.path.remove(str(tmp_path))
        for name in [
            name
            for name in sys.modules
            if name == "ordinary_api" or name.startswith("ordinary_api.")
        ]:
            del sys.modules[name]


def test_generated_client_applies_an_api_key_and_reads_a_text_response(tmp_path):
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "security": [{"apiKey": []}],
            "paths": {
                "/receipts/{receiptId}": {
                    "get": {
                        "operationId": "getReceipt",
                        "parameters": [
                            {
                                "name": "receiptId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {
                            "2XX": {"content": {"text/plain": {}}},
                        },
                    }
                }
            },
            "components": {
                "securitySchemes": {
                    "apiKey": {"type": "apiKey", "in": "query", "name": "key"}
                }
            },
        }
    )
    package_dir = tmp_path / "receipts_api"
    write_client(spec=spec, package_dir=package_dir, package_name="receipts_api")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "secret"
        assert request.headers["Accept"] == "text/plain"
        return httpx.Response(200, text="thank you")

    sys.path.insert(0, str(tmp_path))
    try:
        package = importlib.import_module("receipts_api")
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = package.ReceiptsApiClient(
            http_client,
            "https://example.test",
            credentials={"apiKey": "secret"},
        )

        async def exercise():
            assert await client.get_receipt("r-1") == "thank you"
            await client.aclose()

        asyncio.run(exercise())
    finally:
        sys.path.remove(str(tmp_path))
        for name in [
            name
            for name in sys.modules
            if name == "receipts_api" or name.startswith("receipts_api.")
        ]:
            del sys.modules[name]


def test_read_only_and_write_only_fields_use_directional_models(tmp_path):
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/users": {
                    "post": {
                        "operationId": "createUser",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/User"}
                                }
                            },
                        },
                        "responses": {
                            "201": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/User"}
                                    }
                                }
                            }
                        },
                    }
                }
            },
            "components": {
                "schemas": {
                    "User": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "name", "password"],
                        "properties": {
                            "id": {"type": "string", "readOnly": True},
                            "name": {"type": "string"},
                            "password": {"type": "string", "writeOnly": True},
                        },
                    }
                }
            },
        }
    )
    package_dir = tmp_path / "users_api"
    write_client(spec=spec, package_dir=package_dir, package_name="users_api")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.read().decode() == '{"name":"Ada","password":"secret"}'
        return httpx.Response(201, json={"id": "user-1", "name": "Ada"})

    sys.path.insert(0, str(tmp_path))
    try:
        package = importlib.import_module("users_api")
        assert "id" not in package.UserRequest.model_fields
        assert "password" not in package.UserResponse.model_fields
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = package.UsersApiClient(http_client, "https://example.test")

        async def exercise():
            request = package.UserRequest(name="Ada", password="secret")
            response = await client.create_user(request)
            assert isinstance(response, package.UserResponse)
            assert response.id == "user-1"
            await client.aclose()

        asyncio.run(exercise())
    finally:
        sys.path.remove(str(tmp_path))
        for name in [
            name
            for name in sys.modules
            if name == "users_api" or name.startswith("users_api.")
        ]:
            del sys.modules[name]


def test_generated_workspace_shares_one_api_error_between_tag_clients(
    tmp_path, generatable_spec
):
    package_dir = tmp_path / "api"
    write_client(
        spec=generatable_spec,
        package_dir=package_dir,
        package_name="api",
        tags=["payments", "invoices"],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "gone", "message": "not here"})

    sys.path.insert(0, str(tmp_path))
    try:
        package = importlib.import_module("api")
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        payments = package.PaymentsClient(
            http_client, "https://example.test", credentials={"bearerAuth": "secret"}
        )
        invoices = package.InvoicesClient(
            http_client, "https://example.test", credentials={"bearerAuth": "secret"}
        )
        assert type(payments).__module__ == "api.payments.client"
        assert type(invoices).__module__ == "api.invoices.client"
        assert (
            importlib.import_module("api.payments.client").ApiError
            is importlib.import_module("api.invoices.client").ApiError
        )

        async def exercise():
            for call in (payments.get_customer, invoices.get_invoice):
                try:
                    await call("11111111-1111-1111-1111-111111111111")
                except package.ApiError as error:
                    assert error.status_code == 404
                    assert error.parsed_body.message == "not here"
                else:
                    raise AssertionError("expected ApiError")
            await http_client.aclose()

        asyncio.run(exercise())
    finally:
        sys.path.remove(str(tmp_path))
        for name in [
            name for name in sys.modules if name == "api" or name.startswith("api.")
        ]:
            del sys.modules[name]
