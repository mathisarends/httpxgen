import os
import subprocess
import sys

import pytest

from httpxgen import OpenAPISpec, write_client


@pytest.mark.parametrize("backend", ["httpx", "httpx2"])
@pytest.mark.parametrize("concrete", [False, True])
def test_generated_protocols_accept_httpx_without_casts(tmp_path, backend, concrete):
    pytest.importorskip("mypy")
    pytest.importorskip(backend)
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "info": {"title": "Typing", "version": "1"},
            "paths": {
                "/value": {
                    "post": {
                        "operationId": "sendValue",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {"schema": {"type": "integer"}}
                            },
                        },
                        "responses": {"204": {}},
                    }
                },
                "/download": {
                    "get": {
                        "operationId": "download",
                        "responses": {
                            "200": {
                                "content": {"application/octet-stream": {}},
                                "headers": {"X-Count": {"schema": {"type": "integer"}}},
                            }
                        },
                    }
                },
            },
        }
    )
    write_client(
        spec=spec,
        package_dir=tmp_path / "typed_api",
        package_name="typed_api",
        http_client=backend if concrete else "protocol",
    )
    consumer = tmp_path / "check.py"
    consumer.write_text(
        f"import {backend} as httpx\n"
        "from typed_api import TypedApiClient, AsyncHttpClient, HttpResponse\n"
        "transport: AsyncHttpClient = httpx.AsyncClient()\n"
        "response: HttpResponse = httpx.Response(200)\n"
        'client = TypedApiClient(httpx.AsyncClient(), "https://example.test")\n'
    )
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--no-incremental", str(consumer)],
        cwd=tmp_path,
        env={**os.environ, "MYPYPATH": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
