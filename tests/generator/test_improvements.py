import asyncio
import importlib
import io
import sys

import httpx
import pytest

from httpxgen import OpenAPISpec, write_client
from httpxgen.generator import GenerationError, generate_client


def _spec(paths, schemas=None):
    return OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": paths,
            "components": {"schemas": schemas or {}},
        }
    )


def _load(tmp_path, name, spec):
    write_client(spec=spec, package_dir=tmp_path / name, package_name=name)
    sys.path.insert(0, str(tmp_path))
    return importlib.import_module(name)


def _unload(tmp_path, name):
    sys.path.remove(str(tmp_path))
    for module_name in list(sys.modules):
        if module_name == name or module_name.startswith(f"{name}."):
            del sys.modules[module_name]


def test_client_name_uses_package_leaf_and_exact_override():
    spec = _spec({})

    assert (
        "class BrowserWorkerClient"
        in generate_client(spec, "generated.browser_worker")["client.py"]
    )
    assert (
        "class PaymentsClient" in generate_client(spec, "company.payments")["client.py"]
    )
    assert (
        "class Provisioner"
        in generate_client(spec, "generated.api", client_name="Provisioner")[
            "client.py"
        ]
    )
    with pytest.raises(GenerationError, match="valid Python class identifier"):
        generate_client(spec, "api", client_name="not valid")
    with pytest.raises(GenerationError, match="generated support type"):
        generate_client(spec, "api", client_name="UploadFile")


def test_invalid_client_name_and_multi_tag_override_write_nothing(
    tmp_path, generatable_spec
):
    invalid_output = tmp_path / "invalid"
    with pytest.raises(GenerationError, match="valid Python class identifier"):
        write_client(
            spec=generatable_spec,
            package_dir=invalid_output,
            client_name="class",
        )
    assert not invalid_output.exists()

    workspace_output = tmp_path / "workspace"
    with pytest.raises(GenerationError, match="multi-tag generation"):
        write_client(
            spec=generatable_spec,
            package_dir=workspace_output,
            client_name="CustomClient",
            tags=["payments", "invoices"],
        )
    assert not workspace_output.exists()


def test_operation_failures_share_one_exception_base(tmp_path):
    spec = _spec(
        {
            "/item": {
                "get": {
                    "operationId": "getItem",
                    "parameters": [
                        {
                            "name": "X-Broken",
                            "in": "header",
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["id"],
                                        "properties": {"id": {"type": "integer"}},
                                    }
                                }
                            }
                        }
                    },
                }
            }
        }
    )
    package = _load(tmp_path, "errors_api", spec)
    try:

        async def exercise():
            class BadString:
                def __str__(self):
                    raise ValueError("cannot serialize")

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, content=b"not-json")
                )
            ) as http_client:
                client = package.ErrorsApiClient(http_client, "https://example.test")
                assert isinstance(http_client, package.AsyncHttpClient)
                with pytest.raises(package.RequestValidationError):
                    await client.get_item(x__broken=BadString())
                with pytest.raises(package.ClientError) as caught:
                    await client.get_item()
                assert isinstance(caught.value, package.ResponseValidationError)
                assert caught.value.status_code == 200
                await client.aclose()
                assert not http_client.is_closed

            async def fail(request):
                raise httpx.ConnectError("offline", request=request)

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(fail)
            ) as http_client:
                client = package.ErrorsApiClient(http_client, "https://example.test")
                with pytest.raises(package.TransportError) as caught:
                    await client.get_item()
                assert isinstance(caught.value.__cause__, httpx.ConnectError)
                assert caught.value.cause is caught.value.__cause__

        asyncio.run(exercise())
    finally:
        _unload(tmp_path, "errors_api")


def test_binary_response_streams_and_buffered_method_uses_same_path(tmp_path):
    spec = _spec(
        {
            "/recording": {
                "get": {
                    "operationId": "downloadRecording",
                    "responses": {
                        "200": {
                            "content": {
                                "application/octet-stream": {
                                    "schema": {"type": "string", "format": "binary"}
                                },
                                "video/webm": {
                                    "schema": {"type": "string", "format": "binary"}
                                },
                            }
                        },
                        "404": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            }
                        },
                    },
                }
            }
        },
        {
            "Error": {
                "type": "object",
                "required": ["code", "message"],
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                },
            }
        },
    )
    package = _load(tmp_path, "stream_api", spec)
    responses = []

    class ChunkStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"ab"
            yield b"cd"
            yield b"ef"

    def handler(request):
        response = httpx.Response(
            200,
            stream=ChunkStream(),
            headers={
                "Content-Type": "video/webm; codecs=vp9",
                "Content-Length": "6",
                "Content-Disposition": 'attachment; filename="capture.webm"',
            },
        )
        responses.append(response)
        return response

    try:

        async def exercise():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as http_client:
                client = package.StreamApiClient(http_client, "https://example.test")
                async with client.stream_download_recording() as recording:
                    assert recording.media_type == "video/webm"
                    assert recording.content_length == 6
                    assert recording.filename == "capture.webm"
                    assert not responses[-1].is_closed
                    assert (
                        b"".join(
                            [
                                chunk
                                async for chunk in recording.iter_bytes(chunk_size=2)
                            ]
                        )
                        == b"abcdef"
                    )
                assert responses[-1].is_closed
                assert await client.download_recording() == b"abcdef"

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        404,
                        json={"code": "missing", "message": "not found"},
                        headers={"Content-Type": "application/json"},
                    )
                )
            ) as http_client:
                client = package.StreamApiClient(http_client, "https://example.test")
                with pytest.raises(package.ApiError) as caught:
                    async with client.stream_download_recording():
                        pass
                assert caught.value.code == "missing"
                assert caught.value.message == "not found"
                assert caught.value.detail.code == "missing"
                assert caught.value.raw_body
                assert caught.value.parsed_body is caught.value.detail

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        content=b"wrong",
                        headers={"Content-Type": "text/plain"},
                    )
                )
            ) as http_client:
                client = package.StreamApiClient(http_client, "https://example.test")
                with pytest.raises(package.ResponseValidationError):
                    async with client.stream_download_recording():
                        pass

        asyncio.run(exercise())
    finally:
        _unload(tmp_path, "stream_api")


def test_multipart_arrays_preserve_files_and_do_not_read_eagerly(tmp_path):
    spec = _spec(
        {
            "/documents": {
                "post": {
                    "operationId": "uploadDocuments",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "required": ["documents", "category"],
                                    "properties": {
                                        "documents": {
                                            "type": "array",
                                            "items": {
                                                "type": "string",
                                                "format": "binary",
                                            },
                                        },
                                        "category": {"type": "string"},
                                        "note": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"204": {}},
                }
            }
        }
    )
    package = _load(tmp_path, "uploads_api", spec)

    class ChunkOnlyFile(io.BytesIO):
        def read(self, size=-1):
            if size < 0:
                raise AssertionError("file was read eagerly")
            return super().read(size)

    def handler(request):
        body = request.content
        assert request.headers["Content-Type"].startswith("multipart/form-data;")
        assert body.count(b'name="documents"') == 2
        assert b'filename="a.pdf"' in body
        assert b"application/pdf" in body
        assert b'name="category"' in body
        assert b'name="note"' not in body
        assert b"X-Part: first" in body
        return httpx.Response(204)

    try:

        async def exercise():
            first = ChunkOnlyFile(b"first")
            second = ChunkOnlyFile(b"second")
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as http_client:
                client = package.UploadsApiClient(http_client, "https://example.test")
                await client.upload_documents(
                    documents=[
                        package.UploadFile(
                            first,
                            filename="a.pdf",
                            content_type="application/pdf",
                            headers={"X-Part": "first"},
                        ),
                        second,
                    ],
                    category="contracts",
                )

        asyncio.run(exercise())
    finally:
        _unload(tmp_path, "uploads_api")
