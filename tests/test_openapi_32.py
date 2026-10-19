import json
import sys
from copy import deepcopy
from typing import Any

import pytest

from httpxgen import OpenAPISpec, filter_operations_by_tags
from httpxgen.cli import main
from httpxgen.generator import GenerationError, generate_client, generate_workspace

_EVENT = {"$ref": "#/components/schemas/Event"}
_HEALTH = {
    "operationId": "health",
    "tags": ["rest"],
    "responses": {
        "200": {
            "description": "Healthy",
            "content": {"application/json": {"schema": {"type": "string"}}},
        }
    },
}


def _sse_operation(data_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "operationId": "events",
        "tags": ["sse"],
        "responses": {
            "200": {
                "description": "Events",
                "content": {
                    "text/event-stream": {
                        "itemSchema": {
                            "type": "object",
                            "required": ["data"],
                            "properties": {
                                "data": {
                                    "type": "string",
                                    "contentMediaType": "application/json",
                                    "contentSchema": data_schema,
                                }
                            },
                        }
                    }
                },
            }
        },
    }


def _schemas() -> dict[str, Any]:
    return {
        "Event": {
            "type": "object",
            "required": ["type", "run_id", "payload"],
            "properties": {
                "type": {"const": "started", "type": "string"},
                "run_id": {"type": "string", "pattern": "^run_[A-Za-z0-9_-]+$"},
                "payload": {"$ref": "#/components/schemas/EventPayload"},
            },
        },
        "EventPayload": {
            "type": "object",
            "properties": {
                "children": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/EventPayload"},
                }
            },
        },
        "Unused": {"type": "object"},
    }


def _mixed_document(data_schema: dict[str, Any] = _EVENT) -> dict[str, Any]:
    return {
        "openapi": "3.2.0",
        "info": {"title": "Mixed API", "version": "1.0.0"},
        "paths": {
            "/health": {"get": _HEALTH},
            "/events": {"get": _sse_operation(data_schema)},
        },
        "components": {"schemas": _schemas()},
    }


@pytest.fixture
def mixed_spec() -> OpenAPISpec:
    return OpenAPISpec.model_validate(_mixed_document())


def test_schema_tags_follow_item_schema_and_content_schema(mixed_spec):
    selected = filter_operations_by_tags(mixed_spec, ["rest"], schema_tags=["sse"])

    assert set(selected.paths) == {"/health"}
    assert set(selected.components.schemas) == {"Event", "EventPayload"}


def test_filtering_out_sse_without_schema_tag_drops_event_models(mixed_spec):
    selected = filter_operations_by_tags(mixed_spec, ["rest"])

    assert set(selected.components.schemas) == set()


def test_content_schema_references_inside_components_stay_reachable():
    document = _mixed_document()
    document["components"]["schemas"]["Envelope"] = {
        "type": "object",
        "properties": {
            "data": {
                "type": "string",
                "contentMediaType": "application/json",
                "contentSchema": _EVENT,
            }
        },
    }
    document["paths"]["/events"]["get"] = _sse_operation(
        {"$ref": "#/components/schemas/Envelope"}
    )
    spec = OpenAPISpec.model_validate(document)

    selected = filter_operations_by_tags(spec, ["rest"], schema_tags=["sse"])

    assert set(selected.components.schemas) == {"Envelope", "Event", "EventPayload"}


def test_rest_output_matches_the_equivalent_openapi_31_document(mixed_spec):
    selected = filter_operations_by_tags(mixed_spec, ["rest"], schema_tags=["sse"])
    equivalent = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "info": {"title": "Mixed API", "version": "1.0.0"},
            "paths": {"/health": {"get": _HEALTH}},
            "components": {
                "schemas": {
                    name: schema
                    for name, schema in _schemas().items()
                    if name != "Unused"
                }
            },
        }
    )

    files = generate_client(selected, "mixed")

    assert files == generate_client(equivalent, "mixed")
    assert "async def health(" in files["client.py"]
    assert "events" not in files["client.py"]
    assert "class Event(BaseModel):" in files["models.py"]
    assert "class EventPayload(BaseModel):" in files["models.py"]


def test_workspace_generation_keeps_schema_tag_event_models(mixed_spec):
    files = generate_workspace(mixed_spec, ["rest"], "mixed", schema_tags=["sse"])

    models = files["shared/models.py"] + files["rest/models.py"]
    assert "class Event(BaseModel):" in models
    assert "events" not in files["rest/client.py"]


def test_generating_an_item_schema_operation_fails_with_guidance(mixed_spec):
    with pytest.raises(
        GenerationError,
        match=r"GET /events response 200 streams text/event-stream items "
        r"through itemSchema.*--tag and keep the schemas it references "
        r"with --schema-tag",
    ):
        generate_client(mixed_spec, "mixed")


def test_item_schema_request_bodies_fail_with_guidance():
    document = _mixed_document()
    document["paths"]["/upload"] = {
        "post": {
            "operationId": "upload",
            "tags": ["rest"],
            "requestBody": {
                "content": {"application/jsonl": {"itemSchema": _EVENT}},
            },
            "responses": {"204": {"description": "Accepted"}},
        }
    }
    spec = filter_operations_by_tags(OpenAPISpec.model_validate(document), ["rest"])

    with pytest.raises(
        GenerationError, match=r"POST /upload request body streams application/jsonl"
    ):
        generate_client(spec, "mixed")


@pytest.mark.parametrize(
    ("path_item", "method"),
    [
        ({"query": {**_HEALTH, "operationId": "search", "tags": ["search"]}}, "QUERY"),
        (
            {
                "additionalOperations": {
                    "LINK": {**_HEALTH, "operationId": "link", "tags": ["search"]}
                }
            },
            "LINK",
        ),
    ],
)
def test_unsupported_openapi_32_operations(path_item, method):
    document = _mixed_document()
    document["paths"]["/search"] = path_item
    spec = OpenAPISpec.model_validate(document)

    with pytest.raises(GenerationError, match=rf"/search declares {method}"):
        generate_client(filter_operations_by_tags(spec, ["search"]), "mixed")
    files = generate_client(filter_operations_by_tags(spec, ["rest"]), "mixed")
    assert "/search" not in files["client.py"]


def test_media_type_component_references_are_resolved():
    document = _mixed_document()
    document["paths"]["/health"]["get"] = deepcopy(_HEALTH)
    document["paths"]["/health"]["get"]["responses"]["200"]["content"] = {
        "application/json": {"$ref": "#/components/mediaTypes/EventJson"}
    }
    document["components"]["mediaTypes"] = {
        "EventJson": {"$ref": "#/components/mediaTypes/EventJsonTarget"},
        "EventJsonTarget": {"schema": _EVENT},
        "Unused": {"schema": {"$ref": "#/components/schemas/Unused"}},
    }
    spec = OpenAPISpec.model_validate(document)

    selected = filter_operations_by_tags(spec, ["rest"])
    files = generate_client(selected, "mixed")

    assert set(selected.components.media_types) == {"EventJson", "EventJsonTarget"}
    assert set(selected.components.schemas) == {"Event", "EventPayload"}
    assert "async def health(" in files["client.py"]
    assert ") -> Event:" in files["client.py"]


@pytest.mark.parametrize(
    ("reference", "media_types", "message"),
    [
        ("#/components/mediaTypes/EventJson", {}, "unresolved reference"),
        (
            "#/components/mediaTypes/EventJson",
            {"EventJson": {"$ref": "#/components/mediaTypes/EventJson"}},
            "cyclic Media Type reference",
        ),
        ("#/components/schemas/Event", {}, "invalid Media Type reference"),
    ],
)
def test_invalid_media_type_references_are_reported(reference, media_types, message):
    document = _mixed_document()
    document["paths"] = {"/health": {"get": deepcopy(_HEALTH)}}
    document["paths"]["/health"]["get"]["responses"]["200"]["content"] = {
        "application/json": {"$ref": reference}
    }
    document["components"]["mediaTypes"] = media_types

    with pytest.raises(GenerationError, match=message):
        generate_client(OpenAPISpec.model_validate(document), "mixed")


def test_querystring_parameters_are_rejected():
    document = _mixed_document()
    document["paths"] = {"/health": {"get": deepcopy(_HEALTH)}}
    document["paths"]["/health"]["get"]["parameters"] = [
        {
            "name": "filter",
            "in": "querystring",
            "content": {"application/x-www-form-urlencoded": {"schema": {}}},
        }
    ]

    with pytest.raises(GenerationError, match="parameter location: 'querystring'"):
        generate_client(OpenAPISpec.model_validate(document), "mixed")


def test_cli_generates_rest_client_from_mixed_openapi_32(tmp_path, monkeypatch):
    spec_path = tmp_path / "openapi.json"
    spec_path.write_text(json.dumps(_mixed_document()))
    output = tmp_path / "mixed"
    arguments = ["httpxgen", str(spec_path), str(output), "--tag", "rest"]
    monkeypatch.setattr(sys, "argv", [*arguments, "--schema-tag", "sse"])

    assert main() == 0
    assert "class Event(BaseModel):" in (output / "models.py").read_text()
