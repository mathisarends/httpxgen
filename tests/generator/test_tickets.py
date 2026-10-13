import asyncio
import importlib
import json
import sys
from contextlib import contextmanager

import httpx
import pytest

from httpxgen import OpenAPISpec, write_client


@contextmanager
def generated(tmp_path, paths, schemas=None, **spec_options):
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
        spec=spec, package_dir=tmp_path / "ticket_api", package_name="ticket_api"
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
        assert json.loads(seen[0].content) == {
            "name": None,
            "enabled": True,
            "nested": {"display-name": None},
        }
