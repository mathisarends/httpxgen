import asyncio
import importlib
import sys
import warnings
from contextlib import contextmanager

import httpx
import pytest

from httpxgen import OpenAPISpec, write_client

_SESSION_PARAMETER = {
    "name": "session",
    "in": "cookie",
    "required": True,
    "schema": {"type": "string"},
}


def _operation(responses=None, **extra):
    return {
        "operationId": "readItem",
        "parameters": [_SESSION_PARAMETER],
        "responses": responses or {"204": {"description": "Read"}},
        **extra,
    }


@contextmanager
def generated(tmp_path, operation, **spec_options):
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "info": {"title": "Cookies", "version": "1"},
            "paths": {"/items": {"get": operation}},
            **spec_options,
        }
    )
    write_client(spec=spec, package_dir=tmp_path / "cookie_api")
    sys.path.insert(0, str(tmp_path))
    try:
        yield importlib.import_module("cookie_api")
    finally:
        sys.path.remove(str(tmp_path))
        for name in list(sys.modules):
            if name == "cookie_api" or name.startswith("cookie_api."):
                del sys.modules[name]


def send(package, action, *, base_url="https://api.test", client_options=None, **kw):
    seen: list[httpx.Request] = []

    def capture(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "application/octet-stream" in request.headers.get("accept", ""):
            return httpx.Response(
                200,
                content=b"data",
                headers={"Content-Type": "application/octet-stream"},
            )
        return httpx.Response(204)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(capture), **(client_options or {})
        ) as http_client:
            client = package.CookieApiClient(http_client, base_url, **kw)
            with warnings.catch_warnings():
                warnings.simplefilter("error", DeprecationWarning)
                await action(client)

    asyncio.run(exercise())
    return seen


def _client_jar() -> httpx.Cookies:
    cookies = httpx.Cookies()
    cookies.set("tracking", "t", domain="api.test")
    cookies.set("session", "stale", domain="api.test")
    cookies.set("other", "o", domain="elsewhere.test")
    return cookies


def test_cookie_parameters_merge_with_client_cookies(tmp_path):
    with generated(tmp_path, _operation()) as package:
        seen = send(
            package,
            lambda client: client.read_item(session="fresh"),
            client_options={"cookies": _client_jar()},
        )

    assert seen[0].headers["Cookie"] == "tracking=t; session=fresh"


def test_cookie_parameters_merge_with_a_default_cookie_header(tmp_path):
    with generated(tmp_path, _operation()) as package:
        seen = send(
            package,
            lambda client: client.read_item(session="fresh"),
            client_options={"cookies": _client_jar()},
            headers={"cookie": "explicit=e; session=old"},
        )

    assert seen[0].headers["Cookie"] == "explicit=e; session=fresh"


def test_client_base_url_is_used_for_relative_requests(tmp_path):
    with generated(tmp_path, _operation()) as package:
        seen = send(
            package,
            lambda client: client.read_item(session="fresh"),
            base_url="",
            client_options={"cookies": _client_jar(), "base_url": "https://api.test"},
        )

    assert seen[0].headers["Cookie"] == "tracking=t; session=fresh"


def test_cookie_api_keys_merge_with_client_cookies(tmp_path):
    operation = {
        "operationId": "readItem",
        "security": [{"cookieKey": []}],
        "responses": {"204": {"description": "Read"}},
    }
    components = {
        "securitySchemes": {
            "cookieKey": {"type": "apiKey", "in": "cookie", "name": "api_key"}
        }
    }
    with generated(tmp_path, operation, components=components) as package:
        seen = send(
            package,
            lambda client: client.read_item(),
            client_options={"cookies": _client_jar()},
            credentials={"cookieKey": "secret"},
        )

    assert seen[0].headers["Cookie"] == "tracking=t; session=stale; api_key=secret"


@pytest.mark.parametrize("streamed", [False, True])
def test_binary_operations_send_cookies_without_deprecated_arguments(
    tmp_path, streamed
):
    responses = {
        "200": {
            "description": "Data",
            "content": {"application/octet-stream": {}},
        }
    }

    async def read(client):
        if not streamed:
            return await client.read_item(session="fresh")
        async with client.stream_read_item(session="fresh") as result:
            return b"".join([chunk async for chunk in result.iter_bytes()])

    with generated(tmp_path, _operation(responses)) as package:
        seen = send(package, read, client_options={"cookies": _client_jar()})

    assert seen[0].headers["Cookie"] == "tracking=t; session=fresh"
