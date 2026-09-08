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

    assert "class BrowserWorkerClient" in generate_client(
        spec, "generated.browser_worker"
    )["client.py"]
    assert "class PaymentsClient" in generate_client(spec, "company.payments")[
        "client.py"
    ]
    assert "class Provisioner" in generate_client(
        spec, "generated.api", client_name="Provisioner"
    )["client.py"]
    with pytest.raises(GenerationError, match="valid Python class identifier"):
        generate_client(spec, "api", client_name="not valid")


def test_operation_failures_share_one_exception_base(tmp_path):
    spec = _spec(
        {
            "/item": {
                "get": {
                    "operationId": "getItem",
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
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, content=b"not-json")
                )
            ) as http_client:
                client = package.ErrorsApiClient(http_client, "https://example.test")
                with pytest.raises(package.ClientError) as caught:
                    await client.get_item()
                assert isinstance(caught.value, package.ResponseValidationError)
                assert caught.value.status_code == 200

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

    def handler(request):
        response = httpx.Response(
            200,
            content=b"abcdef",
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
                    assert b"".join(
                        [chunk async for chunk in recording.iter_bytes(chunk_size=2)]
                    ) == b"abcdef"
                assert responses[-1].is_closed
                assert await client.download_recording() == b"abcdef"

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

    class MultipartTransport:
        async def request(self, method, url, **kwargs):
            assert kwargs.pop("timeout") == 30.0
            assert "Content-Type" not in kwargs["headers"]
            files = kwargs["files"]
            assert [name for name, _ in files] == [
                "documents",
                "documents",
                "category",
            ]
            assert files[0][1][0] == "a.pdf"
            assert files[0][1][2:] == ("application/pdf", {})
            assert files[1][1][0] is None
            assert files[1][1][2:] == (None, {})
            assert files[2] == ("category", (None, "contracts", None, {}))
            assert files[0][1][1].tell() == 0
            assert files[1][1][1].tell() == 0
            return httpx.Response(204)

    try:
        async def exercise():
            first = ChunkOnlyFile(b"first")
            second = ChunkOnlyFile(b"second")
            client = package.UploadsApiClient(
                MultipartTransport(), "https://example.test"
            )
            await client.upload_documents(
                documents=[
                    package.UploadFile(
                        first, filename="a.pdf", content_type="application/pdf"
                    ),
                    second,
                ],
                category="contracts",
            )

        asyncio.run(exercise())
    finally:
        _unload(tmp_path, "uploads_api")
