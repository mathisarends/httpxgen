import asyncio
import importlib
import json
import sys
from contextlib import contextmanager

import httpx
import pytest

from httpxgen import OpenAPISpec, write_client


@pytest.mark.parametrize("backend", ["protocol", "httpx"])
@pytest.mark.parametrize("optional", [False, True])
def test_009_binary_iterables_are_lazy(tmp_path, backend, optional):
    paths = {
        "/upload": {
            "post": {
                "operationId": "upload",
                "requestBody": {
                    "required": not optional,
                    "content": {"application/octet-stream": {}},
                },
                "responses": {"204": {}},
            }
        }
    }
    with generated(tmp_path, paths, http_client=backend) as package:
        transport_module = importlib.import_module("ticket_api.transport")
        consumed = []

        def chunks():
            for index in range(3):
                consumed.append(index)
                yield bytes([index])

        adapted = transport_module.binary_content(chunks())
        assert consumed == []

        async def check_lazy():
            iterator = adapted.__aiter__()
            assert await anext(iterator) == b"\x00"
            assert consumed == [0]
            await iterator.aclose()

        asyncio.run(check_lazy())
        seen, _ = invoke(package, lambda client: client.upload(chunks()))
        assert seen[0].content == b"\x00\x01\x02"

        async def async_chunks():
            yield b"async"

        seen, _ = invoke(package, lambda client: client.upload(async_chunks()))
        assert seen[0].content == b"async"
        failure = ValueError("input generator failed")

        def broken():
            yield b"first"
            raise failure

        with pytest.raises(package.TransportError) as caught:
            invoke(package, lambda client: client.upload(broken()))
        assert caught.value.cause is failure


@pytest.mark.parametrize("streaming", [False, True])
def test_008_stream_read_failures_are_transport_errors(tmp_path, streaming):
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "responses": {"200": {"content": {"application/octet-stream": {}}}},
            }
        }
    }
    with generated(tmp_path, paths) as package:
        failure = httpx.ReadError("lost mid-download")

        class BrokenStream(httpx.AsyncByteStream):
            closes = 0

            async def __aiter__(self):
                yield b"first"
                raise failure

            async def aclose(self):
                self.closes += 1

        stream = BrokenStream()
        response = httpx.Response(
            200, stream=stream, headers={"Content-Type": "application/octet-stream"}
        )

        async def action(client):
            if streaming:
                async with client.stream_get_item() as result:
                    async for _ in result.iter_bytes():
                        pass
            else:
                await client.get_item()

        with pytest.raises(package.TransportError) as caught:
            invoke(package, action, lambda _: response)
        assert isinstance(caught.value, package.ClientError)
        assert caught.value.cause is failure
        assert caught.value.__cause__ is failure
        assert response.is_closed
        assert stream.closes == 1

        async def consumer_error(client):
            async with client.stream_get_item():
                raise ValueError("consumer")

        with pytest.raises(ValueError, match="consumer"):
            invoke(
                package,
                consumer_error,
                lambda _: httpx.Response(
                    200,
                    content=b"data",
                    headers={"Content-Type": "application/octet-stream"},
                ),
            )


@pytest.mark.parametrize("status", [200, 500])
def test_007_cancelled_stream_closes_response(tmp_path, status):
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "responses": {
                    "200": {"content": {"application/octet-stream": {}}},
                    "500": {},
                },
            }
        }
    }
    with generated(tmp_path, paths) as package:

        async def exercise():
            reading = asyncio.Event()

            class WaitingStream(httpx.AsyncByteStream):
                closes = 0

                async def __aiter__(self):
                    reading.set()
                    await asyncio.Event().wait()
                    yield b"unreachable"

                async def aclose(self):
                    self.closes += 1

            stream = WaitingStream()
            response = httpx.Response(
                status,
                stream=stream,
                headers={"Content-Type": "application/octet-stream"},
            )
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _: response)
            ) as transport:
                client = package.TicketApiClient(transport, "https://example.test")
                task = asyncio.create_task(client.get_item())
                await asyncio.wait_for(reading.wait(), timeout=2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert response.is_closed
                assert stream.closes == 1
                assert not transport.is_closed

        asyncio.run(exercise())


@contextmanager
def generated(tmp_path, paths, schemas=None, *, http_client="protocol", **spec_options):
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "info": {"title": "Ticket regressions", "version": "1"},
            "paths": paths,
            "components": {"schemas": schemas or {}},
            **spec_options,
        }
    )
    write_client(
        spec=spec,
        package_dir=tmp_path / "ticket_api",
        package_name="ticket_api",
        http_client=http_client,
    )
    sys.path.insert(0, str(tmp_path))
    try:
        yield importlib.import_module("ticket_api")
    finally:
        sys.path.remove(str(tmp_path))
        for name in list(sys.modules):
            if name == "ticket_api" or name.startswith("ticket_api."):
                del sys.modules[name]


def invoke(package, action, handler=None, headers=None):
    seen = []

    def capture(request):
        seen.append(request)
        return handler(request) if handler else httpx.Response(204)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(capture)
        ) as transport:
            client = package.TicketApiClient(
                transport, "https://example.test", headers=headers
            )
            return await action(client)

    result = asyncio.run(exercise())
    return seen, result


@pytest.mark.parametrize("required", [True, False])
@pytest.mark.parametrize("variants", [True, False])
@pytest.mark.parametrize("media", ["application/json", "application/merge-patch+json"])
def test_001_explicit_null_fields(tmp_path, required, variants, media):
    content = {media: {"schema": {"$ref": "#/components/schemas/Patch"}}}
    if variants:
        content["text/plain"] = {"schema": {"type": "string"}}
    paths = {
        "/item": {
            "patch": {
                "operationId": "updateItem",
                "requestBody": {"required": required, "content": content},
                "responses": {"204": {}},
            }
        }
    }
    nullable = {"type": ["string", "null"]}
    schemas = {
        "Patch": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": nullable,
                "unused": nullable,
                "enabled": {"type": "boolean", "default": True},
                "nested": {"$ref": "#/components/schemas/Nested"},
            },
        },
        "Nested": {
            "type": "object",
            "properties": {"display-name": nullable, "unused": nullable},
        },
    }
    with generated(tmp_path, paths, schemas) as package:
        body = package.Patch(
            name=None, nested=package.Nested.model_validate({"display-name": None})
        )
        kwargs = {"content_type": media} if variants else {}
        seen, _ = invoke(package, lambda client: client.update_item(body, **kwargs))
        expected = {
            "name": None,
            "enabled": True,
            "nested": {"display-name": None},
        }
        if media == "application/merge-patch+json":
            del expected["enabled"]
        assert json.loads(seen[0].content) == expected


def test_002_merge_patch_preserves_explicit_defaults(tmp_path):
    schema = {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "default": True},
            "nested": {
                "type": "object",
                "properties": {
                    "display-name": {"type": "string", "default": "unchanged"},
                    "unused": {"type": "boolean", "default": True},
                },
            },
        },
    }
    paths = {
        "/item": {
            "patch": {
                "operationId": "updateItem",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/merge-patch+json": {
                            "schema": {"$ref": "#/components/schemas/Patch"}
                        }
                    },
                },
                "responses": {"204": {}},
            }
        }
    }
    with generated(tmp_path, paths, {"Patch": schema}) as package:
        body = package.Patch.model_validate(
            {"enabled": True, "nested": {"display-name": "unchanged"}}
        )
        seen, _ = invoke(package, lambda client: client.update_item(body))
        assert json.loads(seen[0].content) == {
            "enabled": True,
            "nested": {"display-name": "unchanged"},
        }


@pytest.mark.parametrize("required", [True, False])
@pytest.mark.parametrize("variants", [True, False])
@pytest.mark.parametrize("media", ["application/json", "application/merge-patch+json"])
def test_003_root_null_body(tmp_path, required, variants, media):
    content = {media: {"schema": {"type": ["string", "null"]}}}
    if variants:
        content["text/plain"] = {"schema": {"type": "string"}}
    paths = {
        "/item": {
            "post": {
                "operationId": "createItem",
                "requestBody": {"required": required, "content": content},
                "responses": {"204": {}},
            }
        }
    }
    with generated(tmp_path, paths) as package:
        kwargs = {"content_type": media} if variants else {}
        seen, _ = invoke(package, lambda client: client.create_item(None, **kwargs))
        assert seen[0].content == b"null"
        assert seen[0].headers["Content-Type"] == media
        if not required:
            seen, _ = invoke(package, lambda client: client.create_item(**kwargs))
            assert seen[0].content == b""
            assert "Content-Type" not in seen[0].headers


def test_004_arguments_do_not_overwrite_generated_locals(tmp_path):
    paths = {
        "/files/{path}": {
            "post": {
                "operationId": "uploadFiles",
                "parameters": [
                    {
                        "name": name,
                        "in": location,
                        "required": True,
                        "schema": {"type": "string"},
                    }
                    for name, location in [
                        ("path", "path"),
                        ("headers", "header"),
                        ("cookies", "cookie"),
                        ("params", "query"),
                        ("query", "query"),
                        ("body_arguments", "query"),
                        ("serialize_query", "query"),
                        ("scalar", "query"),
                    ]
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["files"],
                                "properties": {
                                    "files": {
                                        "type": "array",
                                        "items": {"type": "string", "format": "binary"},
                                    }
                                },
                            }
                        }
                    },
                },
                "responses": {"204": {}},
            }
        }
    }
    with generated(tmp_path, paths) as package:
        seen, _ = invoke(
            package,
            lambda client: client.upload_files(
                path_arg="abc",
                headers_arg="header-value",
                cookies_arg="cookie-value",
                params_arg="params",
                query_arg="query",
                body_arguments_arg="body",
                serialize_query_arg="serializer",
                scalar_arg="scalar",
                files_arg=[b"upload-content"],
            ),
        )
        assert seen[0].url.raw_path.startswith(b"/files/abc?")
        assert seen[0].headers["headers"] == "header-value"
        assert seen[0].headers["Cookie"] == "cookies=cookie-value"
        assert seen[0].url.params["body_arguments"] == "body"
        assert seen[0].url.params["serialize_query"] == "serializer"
        assert b"upload-content" in seen[0].content


@pytest.mark.parametrize(
    "value,encoded",
    [
        (".", "%2E"),
        ("..", "%2E%2E"),
        ("a/b", "a%2Fb"),
        ("%", "%25"),
        ("ordinary.id", "ordinary.id"),
    ],
)
@pytest.mark.parametrize("tail", ["", "/delete"])
@pytest.mark.parametrize("streaming", [False, True])
def test_005_path_segment_boundaries(tmp_path, value, encoded, tail, streaming):
    path = "/items/{id}" + tail
    paths = {
        path: {
            "get": {
                "operationId": "getItem",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {"200": {"content": {"application/octet-stream": {}}}},
            }
        }
    }
    with generated(tmp_path, paths) as package:

        async def action(client):
            if streaming:
                async with client.stream_get_item(value) as response:
                    return b"".join([chunk async for chunk in response.iter_bytes()])
            return await client.get_item(value)

        seen, result = invoke(
            package,
            action,
            lambda _: httpx.Response(
                200,
                content=b"data",
                headers={"Content-Type": "application/octet-stream"},
            ),
        )
        assert seen[0].url.raw_path == f"/items/{encoded}{tail}".encode()
        assert result == b"data"


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "status,media,value",
    [
        (200, "application/octet-stream", b"bytes"),
        (200, "application/json", {"name": "json"}),
        (200, "text/plain", "text"),
        (204, None, None),
        (201, "application/json", {"name": "exact"}),
        (202, "application/octet-stream", b"range"),
    ],
)
def test_006_mixed_binary_successes(tmp_path, streaming, status, media, value):
    json_content = {"schema": {"$ref": "#/components/schemas/Item"}}
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "responses": {
                    "200": {
                        "content": {
                            "application/octet-stream": {},
                            "application/json": json_content,
                            "text/plain": {},
                        }
                    },
                    "201": {"content": {"application/json": json_content}},
                    "204": {},
                    "2XX": {"content": {"application/octet-stream": {}}},
                },
            }
        }
    }
    schemas = {
        "Item": {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
    }
    with generated(tmp_path, paths, schemas) as package:

        async def action(client):
            if not streaming:
                return await client.get_item()
            async with client.stream_get_item() as result:
                if isinstance(result, package.BinaryStream):
                    return b"".join([chunk async for chunk in result.iter_bytes()])
                return result

        def response(_):
            if media == "application/json":
                return httpx.Response(status, json=value)
            return httpx.Response(
                status,
                content=value,
                headers=({"Content-Type": media} if media else {}),
            )

        _, result = invoke(package, action, response)
        assert (
            result.model_dump() if hasattr(result, "model_dump") else result
        ) == value
