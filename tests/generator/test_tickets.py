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
