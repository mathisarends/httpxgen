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


def test_generated_client_sends_multipart_and_api_key_security(tmp_path):
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "security": [{"apiKey": []}],
            "paths": {
                "/upload": {
                    "post": {
                        "operationId": "upload",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "multipart/form-data": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["file", "description"],
                                        "properties": {
                                            "file": {
                                                "type": "string",
                                                "format": "binary",
                                            },
                                            "description": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        },
                        "responses": {"2XX": {"content": {"text/plain": {}}}},
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
    package_dir = tmp_path / "upload_api"
    write_client(spec=spec, package_dir=package_dir, package_name="upload_api")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "secret"
        assert request.headers["Content-Type"].startswith("multipart/form-data;")
        assert b'form-data; name="description"' in request.content
        assert b'form-data; name="file"' in request.content
        assert b"payload" in request.content
        return httpx.Response(201, text="stored")

    sys.path.insert(0, str(tmp_path))
    try:
        package = importlib.import_module("upload_api")
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = package.UploadApiClient(
            http_client,
            "https://example.test",
            credentials={"apiKey": "secret"},
        )

        async def exercise():
            body = package.UploadBody(file=b"payload", description="avatar")
            assert await client.upload(body) == "stored"
            await client.aclose()

        asyncio.run(exercise())
    finally:
        sys.path.remove(str(tmp_path))
        for name in [
            name
            for name in sys.modules
            if name == "upload_api" or name.startswith("upload_api.")
        ]:
            del sys.modules[name]
