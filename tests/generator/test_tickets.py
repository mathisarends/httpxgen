import asyncio
import importlib
import json
import sys
from contextlib import contextmanager
from email import policy
from email.parser import BytesParser
from urllib.parse import parse_qs

import httpx
import pytest

from httpxgen import OpenAPISpec, write_client
from httpxgen.generator import GenerationError


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("variants", [False, True])
@pytest.mark.parametrize("explode", [False, True])
def test_012_urlencoded_encoding_rules(tmp_path, required, variants, explode):
    shape = {
        "type": "object",
        "properties": {
            "tags": {"type": "array", "items": {"type": "string"}},
            "point": {"$ref": "#/components/schemas/Point"},
            "json-point": {"$ref": "#/components/schemas/Point"},
            "default-point": {"$ref": "#/components/schemas/Point"},
        },
    }
    media = {
        "schema": {"$ref": "#/components/schemas/Form"},
        "encoding": {
            "tags": {"style": "form", "explode": explode},
            "point": {"style": "form", "explode": False},
            "json-point": {"contentType": "application/json"},
        },
    }
    content = {"application/x-www-form-urlencoded": media}
    if variants:
        content["text/plain"] = {"schema": {"type": "string"}}
    paths = {
        "/submit": {
            "post": {
                "operationId": "submit",
                "requestBody": {"required": required, "content": content},
                "responses": {"204": {}},
            }
        }
    }
    point = {
        "type": "object",
        "required": ["x", "y"],
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
    }
    with generated(tmp_path, paths, {"Form": shape, "Point": point}) as package:
        body = package.Form.model_validate(
            {
                "tags": ["a", "b"],
                "point": {"x": 1, "y": 2},
                "json-point": {"x": 1, "y": 2},
                "default-point": {"x": 1, "y": 2},
            }
        )
        kwargs = (
            {"content_type": "application/x-www-form-urlencoded"} if variants else {}
        )
        seen, _ = invoke(package, lambda client: client.submit(body, **kwargs))
        assert seen[0].headers["Content-Type"] == "application/x-www-form-urlencoded"
        values = parse_qs(seen[0].content.decode())
        assert values["tags"] == (["a", "b"] if explode else ["a,b"])
        assert values["point"] == ["x,1,y,2"]
        assert json.loads(values["json-point"][0]) == {"x": 1, "y": 2}
        assert json.loads(values["default-point"][0]) == {"x": 1, "y": 2}

    media["encoding"]["tags"] = {"allowReserved": True}
    with (
        pytest.raises(GenerationError, match="unsupported encoding"),
        generated(tmp_path / "unsupported", paths, {"Form": shape, "Point": point}),
    ):
        pass


@pytest.mark.parametrize("encoding", [{}, {"contentType": "application/custom+json"}])
def test_011_multipart_objects_are_json(tmp_path, encoding):
    media = {
        "schema": {
            "type": "object",
            "required": ["metadata", "records", "tag"],
            "properties": {
                "metadata": {"$ref": "#/components/schemas/Meta"},
                "records": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Meta"},
                },
                "tag": {"type": "string"},
            },
        },
        "encoding": {"metadata": encoding},
    }
    paths = {
        "/upload": {
            "post": {
                "operationId": "upload",
                "requestBody": {
                    "required": True,
                    "content": {"multipart/form-data": media},
                },
                "responses": {"204": {}},
            }
        }
    }
    schemas = {
        "Meta": {
            "type": "object",
            "required": ["display-name"],
            "properties": {"display-name": {"type": ["string", "null"]}},
        }
    }
    with generated(tmp_path, paths, schemas) as package:
        meta = package.Meta.model_validate({"display-name": None})
        seen, _ = invoke(
            package,
            lambda client: client.upload(
                metadata=meta, records=[meta, meta], tag="plain"
            ),
        )
        mime_header = (
            f"Content-Type: {seen[0].headers['Content-Type']}\r\n\r\n".encode()
        )
        message = BytesParser(policy=policy.default).parsebytes(
            mime_header + seen[0].content
        )
        parts = list(message.iter_parts())
        assert len(parts) == 4
        for index in range(3):
            assert json.loads(parts[index].get_payload(decode=True)) == {
                "display-name": None
            }
            expected = (
                encoding.get("contentType", "application/json")
                if index == 0
                else "application/json"
            )
            assert parts[index].get_content_type() == expected
        assert parts[-1].get_payload(decode=True) == b"plain"

    media["encoding"]["metadata"] = {"style": "form"}
    with (
        pytest.raises(GenerationError, match="unsupported encoding"),
        generated(tmp_path / "unsupported", paths, schemas),
    ):
        pass
    assert not (tmp_path / "unsupported" / "ticket_api").exists()


@pytest.mark.parametrize("kind", ["bytes", "handle", "default", "metadata", "none"])
def test_010_multipart_file_parts_have_filenames(tmp_path, kind):
    paths = {
        "/upload": {
            "post": {
                "operationId": "upload",
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
    file_path = tmp_path / "source.bin"
    file_path.write_bytes(b"payload")
    with generated(tmp_path, paths) as package, file_path.open("rb") as handle:
        value = {
            "bytes": b"payload",
            "handle": handle,
            "default": package.UploadFile(b"payload"),
            "metadata": package.UploadFile(
                b"payload",
                filename="chosen.dat",
                content_type="application/custom",
                headers={"X-Part": "yes"},
            ),
            "none": package.UploadFile(b"payload", filename=None),
        }[kind]
        helper = importlib.import_module("ticket_api.transport").upload_file_part
        helper(value)
        assert handle.tell() == 0
        seen, _ = invoke(
            package, lambda client: client.upload(files_arg=[value, b"second"])
        )
        message = BytesParser(policy=policy.default).parsebytes(
            (
                f"Content-Type: {seen[0].headers['Content-Type']}\r\n"
                "MIME-Version: 1.0\r\n\r\n"
            ).encode()
            + seen[0].content
        )
        parts = list(message.iter_parts())
        assert len(parts) == 2
        assert parts[0].get_payload(decode=True) == b"payload"
        expected = {
            "bytes": "upload",
            "handle": "source.bin",
            "default": "upload",
            "metadata": "chosen.dat",
            "none": None,
        }[kind]
        assert parts[0].get_filename() == expected
        assert parts[1].get_filename() == "upload"
        if kind == "metadata":
            assert parts[0].get_content_type() == "application/custom"
            assert parts[0]["X-Part"] == "yes"


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
