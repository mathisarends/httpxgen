import asyncio
import importlib
import json
import sys
from base64 import b64encode
from contextlib import contextmanager
from datetime import date
from email import policy
from email.parser import BytesParser
from urllib.parse import parse_qs, unquote

import httpx
import pytest

from httpxgen import OpenAPISpec, write_client
from httpxgen.generator import GenerationError
from httpxgen.generator.normalize import normalize_inline_schemas
from httpxgen.selection import filter_operations_by_tags


@pytest.mark.parametrize("version", ["3.0.3", "3.1.0"])
@pytest.mark.parametrize("workspace", [False, True])
def test_043_nested_byte_fields_round_trip_as_base64(tmp_path, version, workspace):
    byte = {"type": "string", "format": "byte"}
    schemas = {
        "Blob": byte,
        "Payload": {
            "type": "object",
            "required": ["wire-data", "nested"],
            "properties": {
                "wire-data": {"$ref": "#/components/schemas/Blob"},
                "nested": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["wire-value"],
                        "properties": {"wire-value": byte},
                    },
                },
            },
        },
    }
    media = {"application/json": {"schema": {"$ref": "#/components/schemas/Payload"}}}
    paths = {
        "/value": {
            "post": {
                "operationId": "sendValue",
                "tags": ["one"],
                "requestBody": {"required": True, "content": media},
                "responses": {"200": {"content": media}},
            }
        }
    }
    tags = ()
    client_name = "TicketApiClient"
    if workspace:
        paths["/other"] = {
            "get": {"operationId": "other", "tags": ["two"], "responses": {"204": {}}}
        }
        tags = ("one", "two")
        client_name = "OneClient"
    raw = b"\xff\x00\x80abc"
    encoded = b64encode(raw).decode("ascii")
    wire = {"wire-data": encoded, "nested": [{"wire-value": "YWJj"}]}
    with generated(tmp_path, paths, schemas, tags=tags, openapi=version) as package:
        model = package.Payload.model_validate(
            {"wire-data": raw, "nested": [{"wire-value": b"abc"}]}
        )
        assert model.model_dump(mode="json", by_alias=True) == wire
        requests, result = invoke(
            package,
            lambda client: client.send_value(model),
            lambda _: httpx.Response(200, json=wire),
            client_name=client_name,
        )
        assert json.loads(requests[0].content) == wire
        assert result.wire_data == raw
        assert result.nested[0].wire_value == b"abc"
        for invalid in ["%%%", "YWJ", "YWJj\n", "é", "-_8="]:
            with pytest.raises(package.ResponseValidationError):
                invoke(
                    package,
                    lambda client: client.send_value(model),
                    lambda _, invalid=invalid: httpx.Response(
                        200, json={**wire, "wire-data": invalid}
                    ),
                    client_name=client_name,
                )
        with pytest.raises(package.RequestValidationError):
            invoke(
                package,
                lambda client: client.send_value({"wire-data": "%%%", "nested": []}),
                client_name=client_name,
            )


@pytest.mark.parametrize("reference", [False, True])
def test_043_root_byte_json_round_trip(tmp_path, reference):
    byte = {"type": "string", "format": "byte"}
    schema = {"$ref": "#/components/schemas/Blob"} if reference else byte
    media = {"application/json": {"schema": schema}}
    paths = {
        "/value": {
            "post": {
                "operationId": "sendValue",
                "requestBody": {"required": True, "content": media},
                "responses": {"200": {"content": media}},
            }
        }
    }
    with generated(tmp_path, paths, {"Blob": byte} if reference else {}) as package:
        requests, result = invoke(
            package,
            lambda client: client.send_value(b"\xff\x00"),
            lambda _: httpx.Response(200, json="/wA="),
        )
        assert json.loads(requests[0].content) == "/wA="
        assert result == b"\xff\x00"


def test_043_raw_binary_and_multipart_files_remain_raw(tmp_path):
    paths = {
        "/raw": {
            "post": {
                "operationId": "sendRaw",
                "requestBody": {
                    "required": True,
                    "content": {"application/octet-stream": {}},
                },
                "responses": {"200": {"content": {"application/octet-stream": {}}}},
            }
        },
        "/file": {
            "post": {
                "operationId": "sendFile",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["file"],
                                "properties": {
                                    "file": {"type": "string", "format": "binary"}
                                },
                            }
                        }
                    },
                },
                "responses": {"204": {}},
            }
        },
    }
    raw = b"\xff\x00binary"
    with generated(tmp_path, paths) as package:
        requests, result = invoke(
            package,
            lambda client: client.send_raw(raw),
            lambda _: httpx.Response(
                200, content=raw, headers={"Content-Type": "application/octet-stream"}
            ),
        )
        assert requests[0].content == result == raw
        requests, _ = invoke(package, lambda client: client.send_file(raw))
        request = requests[0]
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {request.headers['Content-Type']}\r\n\r\n".encode()
            + request.content
        )
        assert next(message.iter_parts()).get_payload(decode=True) == raw


@pytest.mark.parametrize("location", ["query", "header", "path"])
@pytest.mark.parametrize("reusable", [False, True])
def test_042_json_parameter_content_preserves_one_value_and_aliases(
    tmp_path, location, reusable
):
    schema = {
        "type": "object",
        "required": ["lat", "wire-long", "at"],
        "properties": {
            "lat": {"type": "number"},
            "wire-long": {"type": "number"},
            "at": {"type": "string", "format": "date"},
        },
    }
    parameter = {
        "name": "coordinates",
        "in": location,
        "required": True,
        "content": {"application/json": {"schema": schema}},
    }
    parameters = (
        [{"$ref": "#/components/parameters/Coordinates"}] if reusable else [parameter]
    )
    components = {"parameters": {"Coordinates": parameter}} if reusable else {}
    path = "/run/{coordinates}" if location == "path" else "/run"
    paths = {
        path: {
            "get": {
                "operationId": "run",
                "parameters": parameters,
                "responses": {"204": {}},
            }
        }
    }
    with generated(tmp_path, paths, components=components) as package:
        requests, _ = invoke(
            package,
            lambda client: client.run(
                {"lat": 1, "wire-long": 2, "at": date(2026, 1, 2)}
            ),
        )
        request = requests[0]
        if location == "query":
            assert set(request.url.params) == {"coordinates"}
            encoded = request.url.params["coordinates"]
        elif location == "header":
            encoded = request.headers["coordinates"]
        else:
            encoded = unquote(request.url.raw_path.removeprefix(b"/run/").decode())
            assert b"%7B" in request.url.raw_path
        assert json.loads(encoded) == {"lat": 1, "wire-long": 2, "at": "2026-01-02"}
        with pytest.raises(package.RequestValidationError):
            invoke(package, lambda client: client.run({"lat": "invalid"}))


@pytest.mark.parametrize("required", [False, True])
def test_042_nullable_json_query_parameter_and_omission(tmp_path, required):
    parameter = {
        "name": "q",
        "in": "query",
        "required": required,
        "content": {
            "application/vendor+json": {"schema": {"type": ["string", "null"]}}
        },
    }
    paths = {
        "/run": {
            "get": {
                "operationId": "run",
                "parameters": [parameter],
                "responses": {"204": {}},
            }
        }
    }
    with generated(tmp_path, paths) as package:
        requests, _ = invoke(package, lambda client: client.run(None))
        assert requests[0].url.query == (b"q=null" if required else b"")
        requests, _ = invoke(package, lambda client: client.run("a/b"))
        assert json.loads(requests[0].url.params["q"]) == "a/b"


@pytest.mark.parametrize(
    ("location", "content", "options", "message"),
    [
        (
            "cookie",
            {"application/json": {"schema": {"type": "string"}}},
            {},
            "JSON cookie",
        ),
        (
            "query",
            {"text/plain": {"schema": {"type": "string"}}},
            {},
            "unsupported parameter media",
        ),
        (
            "query",
            {
                "application/json": {"schema": {}},
                "application/vendor+json": {"schema": {}},
            },
            {},
            "exactly one",
        ),
        (
            "query",
            {"application/json": {"schema": {}}},
            {"style": "form"},
            "cannot be combined",
        ),
    ],
)
def test_042_unsupported_parameter_content_fails_before_output(
    tmp_path, location, content, options, message
):
    parameter = {"name": "q", "in": location, "content": content, **options}
    paths = {
        "/run": {
            "get": {
                "operationId": "run",
                "parameters": [parameter],
                "responses": {"204": {}},
            }
        }
    }
    with pytest.raises(GenerationError, match=message), generated(tmp_path, paths):
        pass
    assert not (tmp_path / "ticket_api").exists()


@pytest.mark.parametrize(
    ("style", "explode", "value", "expected"),
    [
        ("simple", False, "blue", "blue"),
        ("simple", True, ["blue", "black"], "blue,black"),
        ("simple", False, ["blue", "black"], "blue,black"),
        ("simple", False, {"R": 100, "G": 200}, "R,100,G,200"),
        ("simple", True, {"R": 100, "G": 200}, "R=100,G=200"),
        ("label", False, "blue", ".blue"),
        ("label", False, ["blue", "black"], ".blue,black"),
        ("label", True, ["blue", "black"], ".blue.black"),
        ("label", False, {"R": 100, "G": 200}, ".R,100,G,200"),
        ("label", True, {"R": 100, "G": 200}, ".R=100.G=200"),
        ("matrix", True, "blue", ";color=blue"),
        ("matrix", False, ["blue", "black"], ";color=blue,black"),
        ("matrix", True, ["blue", "black"], ";color=blue;color=black"),
        ("matrix", False, {"R": 100, "G": 200}, ";color=R,100,G,200"),
        ("matrix", True, {"R": 100, "G": 200}, ";R=100;G=200"),
        ("simple", False, ["a,b", "c/%"], "a%2Cb,c%2F%25"),
        ("label", True, ["a.b", "c/%"], ".a%2Eb.c%2F%25"),
        ("matrix", True, {"a;b": "c=d/%"}, ";a%3Bb=c%3Dd%2F%25"),
    ],
)
def test_041_path_styles_match_wire_expansions(
    tmp_path, style, explode, value, expected
):
    if isinstance(value, dict):
        schema = {
            "type": "object",
            "additionalProperties": {
                "type": "integer"
                if isinstance(next(iter(value.values())), int)
                else "string"
            },
        }
    elif isinstance(value, list):
        schema = {"type": "array", "items": {"type": "string"}}
    else:
        schema = {"type": "string"}
    paths = {
        "/items/{color}": {
            "get": {
                "operationId": "run",
                "parameters": [
                    {
                        "name": "color",
                        "in": "path",
                        "required": True,
                        "style": style,
                        "explode": explode,
                        "schema": schema,
                    }
                ],
                "responses": {"204": {}},
            }
        }
    }
    with generated(tmp_path, paths) as package:
        requests, _ = invoke(package, lambda client: client.run(value))
        assert requests[0].url.raw_path == f"/items/{expected}".encode()


@pytest.mark.parametrize("required", [False, True])
def test_040_reserved_query_values_reach_the_raw_url(tmp_path, required):
    parameters = [
        {
            "name": "q",
            "in": "query",
            "required": required,
            "allowReserved": True,
            "schema": {"type": "string"},
        },
        {"name": "plain", "in": "query", "schema": {"type": "string"}},
        {
            "name": "tags",
            "in": "query",
            "schema": {"type": "array", "items": {"type": "string"}},
        },
    ]
    paths = {
        "/run": {
            "get": {
                "operationId": "run",
                "parameters": parameters,
                "security": [{"key": []}],
                "responses": {"204": {}},
            }
        }
    }
    security = {
        "securitySchemes": {"key": {"type": "apiKey", "in": "query", "name": "api_key"}}
    }
    with generated(tmp_path, paths, components=security) as package:
        requests, _ = invoke(
            package,
            lambda client: client.run(
                "a/b:?@!$'()*,;[]#&=+ %2F%zz", plain="a/b +", tags=["a/b", "c+d"]
            ),
            credentials={"key": "x/y&z"},
        )
        assert (
            requests[0].url.query == b"q=a/b:?@!$'()*,;%5B%5D%23%26%3D%2B%20%2F%25zz"
            b"&plain=a%2Fb+%2B&tags=a%2Fb&tags=c%2Bd&api_key=x%2Fy%26z"
        )
        assert requests[0].url.fragment == ""
        assert requests[0].url.params.get_list("tags") == ["a/b", "c+d"]
        assert requests[0].url.params["api_key"] == "x/y&z"
        if not required:
            requests, _ = invoke(
                package, lambda client: client.run(), credentials={"key": "x/y"}
            )
            assert requests[0].url.query == b"api_key=x%2Fy"


@pytest.mark.parametrize("composition", [False, True])
@pytest.mark.parametrize("directional", [False, True])
def test_039_undeclared_required_keys_validate_requests_and_responses(
    tmp_path, composition, directional
):
    entity = {"type": "object", "required": ["id"]}
    if directional:
        entity["properties"] = {
            "server": {"type": "string", "readOnly": True},
            "secret": {"type": "string", "writeOnly": True},
        }
    schemas = {"Entity": entity}
    if composition:
        schemas = {
            "Base": entity,
            "Entity": {
                "allOf": [
                    {"$ref": "#/components/schemas/Base"},
                    {"type": "object", "properties": {"label": {"type": "string"}}},
                ]
            },
        }
    media = {"application/json": {"schema": {"$ref": "#/components/schemas/Entity"}}}
    paths = {
        "/entity": {
            "post": {
                "operationId": "saveEntity",
                "requestBody": {"required": True, "content": media},
                "responses": {"200": {"content": media}},
            }
        }
    }
    with generated(tmp_path, paths, schemas) as package:
        for value in [123, None, "text", {"nested": [1]}]:
            requests, result = invoke(
                package,
                lambda client, value=value: client.save_entity({"id": value}),
                lambda _, value=value: httpx.Response(200, json={"id": value}),
            )
            assert json.loads(requests[0].content) == {"id": value}
            assert result.model_dump(by_alias=True)["id"] == value
        with pytest.raises(package.RequestValidationError):
            invoke(package, lambda client: client.save_entity({}))
        with pytest.raises(package.ResponseValidationError):
            invoke(
                package,
                lambda client: client.save_entity({"id": 1}),
                lambda _: httpx.Response(200, json={}),
            )


def test_039_required_extra_keys_keep_additional_property_validation(tmp_path):
    schema = {
        "type": "object",
        "required": ["id"],
        "additionalProperties": {"type": "integer"},
    }
    with generated(tmp_path, {}, {"Entity": schema}) as package:
        assert package.Entity.model_validate({"id": 123}).model_dump() == {"id": 123}
        for invalid in [{}, {"id": "bad"}]:
            with pytest.raises(ValueError):
                package.Entity.model_validate(invalid)
    schema["additionalProperties"] = False
    with generated(tmp_path, {}, {"Entity": schema}) as package:
        for invalid in [{}, {"id": 1}]:
            with pytest.raises(ValueError):
                package.Entity.model_validate(invalid)


@pytest.mark.parametrize(
    "base",
    [
        {"type": "integer"},
        {"type": "array", "items": {"type": "string"}},
        {"type": "string"},
    ],
)
def test_038_nonobject_allof_fails_before_output(tmp_path, base):
    paths = {
        "/value": {
            "get": {
                "operationId": "getValue",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Count"}
                            }
                        }
                    }
                },
            }
        }
    }
    schemas = {
        "Value": base,
        "Count": {"allOf": [{"$ref": "#/components/schemas/Value"}, {"minimum": 1}]},
    }
    with (
        pytest.raises(GenerationError, match="allOf supports only object inheritance"),
        generated(tmp_path, paths, schemas),
    ):
        pass
    assert not (tmp_path / "ticket_api").exists()


def test_038_object_allof_still_parses_responses(tmp_path):
    paths = {
        "/value": {
            "get": {
                "operationId": "getValue",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Entity"}
                            }
                        }
                    }
                },
            }
        }
    }
    schemas = {
        "Base": {
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "integer"}},
        },
        "Entity": {
            "allOf": [
                {"$ref": "#/components/schemas/Base"},
                {
                    "type": "object",
                    "required": ["label"],
                    "properties": {"label": {"type": "string"}},
                },
            ]
        },
    }
    with generated(tmp_path, paths, schemas) as package:
        _, result = invoke(
            package,
            lambda client: client.get_value(),
            lambda _: httpx.Response(200, json={"id": 2, "label": "valid"}),
        )
        assert isinstance(result, package.Base)
        assert (result.id, result.label) == (2, "valid")
        with pytest.raises(package.ResponseValidationError):
            invoke(
                package,
                lambda client: client.get_value(),
                lambda _: httpx.Response(200, json={"label": "missing id"}),
            )


@pytest.mark.parametrize("headers", [False, True])
def test_034_api_error_accessors_reach_typed_body_only(tmp_path, headers):
    error_response = {
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
        }
    }
    if headers:
        error_response["headers"] = {"X-Trace": {"schema": {"type": "string"}}}
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "responses": {"204": {}, "400": error_response},
            }
        }
    }
    schemas = {
        "Error": {
            "type": "object",
            "required": ["code", "message"],
            "properties": {"code": {"type": "string"}, "message": {"type": "string"}},
        }
    }
    with generated(tmp_path, paths, schemas) as package:
        with pytest.raises(package.ApiError) as caught:
            invoke(
                package,
                lambda client: client.get_item(),
                lambda _: httpx.Response(
                    400,
                    json={"code": "bad", "message": "failed"},
                    headers={"X-Trace": "abc"},
                ),
            )
        error = caught.value
        assert error.code == "bad"
        assert error.message == "failed"
        assert error.parsed_body is error.detail
        assert error.body == error.raw_body
        if headers:
            assert error.detail.x_trace == "abc"
            assert error.detail.body.code == "bad"
        arbitrary = package.ApiError(400, "raw", {"body": {"code": "nested"}})
        assert arbitrary.code is None
        direct = package.ApiError(400, "raw", {"body": {}, "code": "top"})
        assert direct.code == "top"


def test_033_headers_merge_without_case_duplicates(tmp_path):
    paths = {
        "/item": {
            "post": {
                "operationId": "createItem",
                "security": [{"bearer": []}],
                "parameters": [
                    {
                        "name": "X-Value",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "integer"}}},
                },
                "responses": {
                    "200": {
                        "content": {"application/json": {"schema": {"type": "integer"}}}
                    }
                },
            }
        }
    }
    components = {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}}}
    headers = {
        "accept": "first",
        "ACCEPT": "configured",
        "content-type": "application/custom+json",
        "authorization": "old",
        "X-Value": "old",
        "x-VALUE": "last",
    }
    with generated(tmp_path, paths, components=components) as package:
        seen, _ = invoke(
            package,
            lambda client: client.create_item(x__value="parameter", body=1),
            lambda _: httpx.Response(200, json=1),
            headers=headers,
            credentials={"bearer": "secret"},
        )
        for name, value in {
            "accept": "configured",
            "content-type": "application/custom+json",
            "authorization": "Bearer secret",
            "x-value": "parameter",
        }.items():
            assert seen[0].headers.get_list(name) == [value]
        assert headers["authorization"] == "old"


def test_032_required_defaults_do_not_supply_missing_fields(tmp_path):
    shape = {
        "type": "object",
        "required": ["count"],
        "properties": {
            "count": {"type": "integer", "default": 1},
            "optional": {"type": "integer", "default": 2},
        },
    }
    content = {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}
    paths = {
        "/item": {
            "post": {
                "operationId": "createItem",
                "requestBody": {"required": True, "content": content},
                "responses": {"200": {"content": content}},
            }
        }
    }
    with generated(tmp_path, paths, {"Item": shape}) as package:
        assert package.Item.model_fields["count"].is_required()
        assert package.Item.model_json_schema()["properties"]["count"]["default"] == 1
        with pytest.raises(package.RequestValidationError):
            invoke(package, lambda client: client.create_item({}))
        with pytest.raises(package.ResponseValidationError):
            invoke(
                package,
                lambda client: client.create_item({"count": 1}),
                lambda _: httpx.Response(200, json={}),
            )
        seen, result = invoke(
            package,
            lambda client: client.create_item({"count": 1}),
            lambda _: httpx.Response(200, json={"count": 1}),
        )
        assert json.loads(seen[0].content) == {"count": 1, "optional": 2}
        assert result.count == 1


@pytest.mark.parametrize("version", ["3.0.3", "3.1.0"])
def test_031_examples_survive_normalization_and_canonicalization(version):
    payload = {"$ref": "#/components/schemas/ApiError", "sibling": 42}
    spec = OpenAPISpec.model_validate(
        {
            "openapi": version,
            "components": {
                "schemas": {
                    "ApiError": {
                        "title": "Thing",
                        "type": "object",
                        "example": payload,
                        "examples": [payload],
                        "properties": {"id": {"type": "string"}},
                    }
                }
            },
            "paths": {
                "/item": {
                    "post": {
                        "operationId": "createItem",
                        "tags": ["one"],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiError"},
                                    "example": payload,
                                    "examples": {"item": {"value": payload}},
                                }
                            },
                        },
                        "responses": {"204": {}},
                    }
                }
            },
        }
    )
    for selected, name in [
        (spec, "ApiErrorModel"),
        (filter_operations_by_tags(spec, ["one"]), "Thing"),
    ]:
        normalized = normalize_inline_schemas(selected)
        assert normalized.components.schemas[name]["example"] == payload
        assert normalized.components.schemas[name]["examples"] == [payload]
        media = (
            normalized.paths["/item"]
            .post.request_body.content["application/json"]
            .model_dump(by_alias=True)
        )
        assert media["example"] == payload
        assert media["examples"]["item"]["value"] == payload


@pytest.mark.parametrize("version", ["3.0.3", "3.1.0"])
@pytest.mark.parametrize("tagged", [False, True])
def test_031_ref_keys_inside_data_are_preserved(tmp_path, version, tagged):
    payload = {
        "$ref": "document-id",
        "keep": 1,
        "nullable": True,
        "exclusiveMinimum": True,
        "minimum": 2,
        "nested": [{"$ref": "#/components/schemas/RawThing", "keep": "data"}],
    }
    schema = {
        "title": "Thing",
        "type": "object",
        "required": ["default"],
        "example": payload,
        "examples": [payload],
        "properties": {
            "default": {"$ref": "#/components/schemas/Text"},
            "metadata": {"type": "object", "default": payload, "example": payload},
        },
    }
    media = {
        "schema": {"$ref": "#/components/schemas/RawThing"},
        "example": payload,
        "examples": {"data": {"value": payload}},
    }
    paths = {
        "/item": {
            "post": {
                "operationId": "createItem",
                "tags": ["one"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": media},
                },
                "responses": {"204": {}},
            }
        }
    }
    schemas = {"RawThing": schema, "Text": {"type": "string", "minLength": 2}}
    with generated(
        tmp_path, paths, schemas, openapi=version, tags=["one"] if tagged else []
    ) as package:
        model = getattr(package, "Thing" if tagged else "RawThing")
        body = model(default="valid")
        assert body.metadata == payload
        seen, _ = invoke(package, lambda client: client.create_item(body))
        assert json.loads(seen[0].content) == {"default": "valid", "metadata": payload}
        with pytest.raises(package.RequestValidationError):
            invoke(package, lambda client: client.create_item({"default": "x"}))
    schema["properties"]["default"] = {"$ref": "#/components/schemas/Missing"}
    with (
        pytest.raises(GenerationError, match="unresolved reference"),
        generated(tmp_path / "invalid", paths, schemas, openapi=version),
    ):
        pass


@pytest.mark.parametrize(
    "schemas",
    [
        {
            "Node": {
                "oneOf": [{"type": "string"}, {"$ref": "#/components/schemas/Node"}]
            }
        },
        {
            "Node": {"$ref": "#/components/schemas/Other"},
            "Other": {"$ref": "#/components/schemas/Node"},
        },
    ],
)
def test_030_unsupported_recursive_aliases_fail_before_writes(tmp_path, schemas):
    with (
        pytest.raises(GenerationError, match="recursive"),
        generated(tmp_path, {}, schemas),
    ):
        pass
    assert not (tmp_path / "ticket_api").exists()


@pytest.mark.parametrize(
    "schemas,value",
    [
        (
            {"Node": {"type": "array", "items": {"$ref": "#/components/schemas/Node"}}},
            [[[]]],
        ),
        (
            {
                "Node": {
                    "anyOf": [
                        {"type": "string"},
                        {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Node"},
                        },
                    ]
                }
            },
            ["leaf", ["nested"]],
        ),
        (
            {
                "Node": {
                    "anyOf": [
                        {"type": "string"},
                        {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Other"},
                        },
                    ]
                },
                "Other": {
                    "anyOf": [
                        {"type": "integer"},
                        {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Node"},
                        },
                    ]
                },
            },
            [1, ["leaf"]],
        ),
    ],
)
def test_030_recursive_aliases_import_and_validate_finite_values(
    tmp_path, schemas, value
):
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Node"}
                            }
                        }
                    }
                },
            }
        }
    }
    with generated(tmp_path, paths, schemas) as package:
        _, result = invoke(
            package,
            lambda client: client.get_item(),
            lambda _: httpx.Response(200, json=value),
        )
        assert result == value
        with pytest.raises(package.ResponseValidationError):
            invoke(
                package,
                lambda client: client.get_item(),
                lambda _: httpx.Response(200, json={"invalid": "object"}),
            )


@pytest.mark.parametrize("streaming", [False, True])
def test_028_binary_response_headers_are_typed_and_validated(tmp_path, streaming):
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "responses": {
                    "200": {
                        "content": {"application/octet-stream": {}},
                        "headers": {"X-Count": {"schema": {"type": "integer"}}},
                    }
                },
            }
        }
    }
    with generated(tmp_path, paths) as package:

        async def action(client):
            if not streaming:
                return await client.get_item()
            async with client.stream_get_item() as result:
                assert isinstance(result, package.GetItemResult200Stream)
                assert isinstance(result.body, package.BinaryStream)
                data = b"".join([chunk async for chunk in result.body.iter_bytes()])
                return package.GetItemResult200(body=data, x_count=result.x_count)

        def response(count):
            return httpx.Response(
                200,
                content=b"bytes",
                headers={"Content-Type": "application/octet-stream", "X-Count": count},
            )

        _, result = invoke(package, action, lambda _: response("3"))
        assert isinstance(result, package.GetItemResult200)
        assert result.body == b"bytes"
        assert result.x_count == 3
        malformed = response("not-an-int")
        with pytest.raises(package.ResponseValidationError):
            invoke(package, action, lambda _: malformed)
        assert malformed.is_closed


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("binary", [False, True])
def test_027_invalid_media_choices_fail_before_transport(tmp_path, required, binary):
    content = {
        "application/json": {"schema": {"type": "string"}},
        "text/plain": {"schema": {"type": "string"}},
    }
    responses = (
        {"200": {"content": {"application/octet-stream": {}}}}
        if binary
        else {"204": {}}
    )
    paths = {
        "/item": {
            "post": {
                "operationId": "createItem",
                "requestBody": {"required": required, "content": content},
                "responses": responses,
            }
        }
    }
    with generated(tmp_path, paths) as package:
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(
                200 if binary else 204,
                content=b"result" if binary else b"",
                headers={"Content-Type": "application/octet-stream"} if binary else {},
            )

        with pytest.raises(
            package.RequestValidationError,
            match=r"application/xml.*application/json.*text/plain",
        ):
            invoke(
                package,
                lambda client: client.create_item(
                    "value", content_type="application/xml"
                ),
                handler,
            )
        if not required:
            with pytest.raises(package.RequestValidationError):
                invoke(
                    package,
                    lambda client: client.create_item(content_type="application/xml"),
                    handler,
                )
        assert calls == []
        for media in content:
            invoke(
                package,
                lambda client, media=media: client.create_item(
                    "value", content_type=media
                ),
                handler,
            )
        assert calls[0].content == b'"value"'
        assert calls[1].content == b"value"


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("variants", [False, True])
def test_026_json_request_inputs_are_validated_before_transport(
    tmp_path, required, variants
):
    content = {"application/json": {"schema": {"$ref": "#/components/schemas/Input"}}}
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
    shape = {
        "type": "object",
        "required": ["count"],
        "properties": {
            "count": {"type": "integer", "minimum": 1},
            "display-name": {"type": ["string", "null"]},
        },
    }
    with generated(tmp_path, paths, {"Input": shape}) as package:
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(204)

        mutated = package.Input(count=2)
        mutated.count = "oops"
        for invalid in [{"count": "oops"}, {"count": 0}, {}, mutated]:
            with pytest.raises(package.RequestValidationError):
                invoke(
                    package,
                    lambda client, invalid=invalid: client.create_item(invalid),
                    handler,
                )
        assert calls == []
        seen, _ = invoke(
            package,
            lambda client: client.create_item({"count": 2, "display-name": None}),
        )
        assert json.loads(seen[0].content) == {"count": 2, "display-name": None}


@pytest.mark.parametrize("value,other", [("a", "b"), (1, 2), (1.5, 2.5)])
@pytest.mark.parametrize("inline", [False, True])
def test_025_const_and_enum_are_intersected(tmp_path, value, other, inline):
    shape = {
        "type": "string" if isinstance(value, str) else "number",
        "const": value,
        "enum": [value, other],
    }
    schema = shape if inline else {"$ref": "#/components/schemas/Value"}
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "responses": {
                    "200": {"content": {"application/json": {"schema": schema}}}
                },
            }
        }
    }
    with generated(tmp_path, paths, {} if inline else {"Value": shape}) as package:
        _, result = invoke(
            package,
            lambda client: client.get_item(),
            lambda _: httpx.Response(200, json=value),
        )
        assert result == value
        with pytest.raises(package.ResponseValidationError):
            invoke(
                package,
                lambda client: client.get_item(),
                lambda _: httpx.Response(200, json=other),
            )
    shape["enum"] = [other]
    with (
        pytest.raises(GenerationError, match="contradictory"),
        generated(
            tmp_path / "contradiction", paths, {} if inline else {"Value": shape}
        ),
    ):
        pass


@pytest.mark.parametrize(
    "shape,invalid,valid",
    [
        ({"type": "integer", "minimum": 10, "maximum": 20}, -1, 10),
        (
            {"type": "string", "minLength": 2, "maxLength": 4, "pattern": "^a"},
            "b",
            "abc",
        ),
        (
            {
                "type": "array",
                "minItems": 2,
                "maxItems": 3,
                "items": {"type": "integer", "minimum": 10},
            },
            [],
            [10, 11],
        ),
        ({"type": "array", "items": {"type": "integer", "minimum": 10}}, [-1], [10]),
    ],
)
@pytest.mark.parametrize("inline", [False, True])
def test_024_scalar_and_item_constraints(tmp_path, shape, invalid, valid, inline):
    schema = shape if inline else {"$ref": "#/components/schemas/Value"}
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "responses": {
                    "200": {"content": {"application/json": {"schema": schema}}}
                },
            }
        }
    }
    with generated(tmp_path, paths, {} if inline else {"Value": shape}) as package:
        with pytest.raises(package.ResponseValidationError):
            invoke(
                package,
                lambda client: client.get_item(),
                lambda _: httpx.Response(200, json=invalid),
            )
        _, result = invoke(
            package,
            lambda client: client.get_item(),
            lambda _: httpx.Response(200, json=valid),
        )
        assert result == valid


def test_024_nested_array_item_constraints(tmp_path):
    shape = {
        "type": "object",
        "required": ["xs"],
        "properties": {
            "xs": {"type": "array", "items": {"type": "integer", "minimum": 10}}
        },
    }
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Item"}
                            }
                        }
                    }
                },
            }
        }
    }
    with generated(tmp_path, paths, {"Item": shape}) as package:
        with pytest.raises(package.ResponseValidationError):
            invoke(
                package,
                lambda client: client.get_item(),
                lambda _: httpx.Response(200, json={"xs": [-1]}),
            )
        _, result = invoke(
            package,
            lambda client: client.get_item(),
            lambda _: httpx.Response(200, json={"xs": [10]}),
        )
        assert result.xs == [10]


@pytest.mark.parametrize(
    "branches,value,valid",
    [
        ([{"type": "string"}, {"type": "integer"}], "123", True),
        ([{"type": "string"}, {"type": "integer"}], 123, True),
        ([{"type": "string"}, {"type": "integer"}], 123.0, True),
        ([{"type": "string"}, {"type": "integer"}], True, False),
        ([{"type": "boolean"}, {"type": "integer"}], True, True),
        ([{"type": "boolean"}, {"type": "integer"}], 1, True),
        (
            [{"type": "string", "format": "date"}, {"type": "integer"}],
            "2024-01-02",
            True,
        ),
        (
            [{"type": "string", "format": "uuid"}, {"type": "integer"}],
            "12345678-1234-1234-1234-123456789abc",
            True,
        ),
        ([{"type": "integer"}, {"type": "number"}], 1, False),
    ],
)
def test_023_oneof_counts_json_membership(tmp_path, branches, value, valid):
    shape = {"oneOf": branches}
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Choice"}
                            }
                        }
                    }
                },
            }
        }
    }
    with generated(tmp_path, paths, {"Choice": shape}) as package:
        if valid:
            _, result = invoke(
                package,
                lambda client: client.get_item(),
                lambda _: httpx.Response(200, json=value),
            )
            assert result == value or str(result) == value
        else:
            with pytest.raises(package.ResponseValidationError, match="oneOf"):
                invoke(
                    package,
                    lambda client: client.get_item(),
                    lambda _: httpx.Response(200, json=value),
                )


@pytest.mark.parametrize("extra", [True, False])
def test_022_underscore_properties_are_validated_fields(tmp_path, extra):
    shape = {
        "type": "object",
        "required": ["_id"],
        "additionalProperties": extra,
        "properties": {"_id": {"type": "string", "minLength": 2}},
    }
    content = {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}
    paths = {
        "/item": {
            "post": {
                "operationId": "createItem",
                "requestBody": {"required": True, "content": content},
                "responses": {"200": {"content": content}},
            }
        }
    }
    with generated(tmp_path, paths, {"Item": shape}) as package:
        body = package.Item(field_id="ok")
        assert "field_id" in package.Item.model_fields
        seen, result = invoke(
            package,
            lambda client: client.create_item(body),
            lambda _: httpx.Response(200, json={"_id": "result"}),
        )
        assert result.field_id == "result"
        assert json.loads(seen[0].content) == {"_id": "ok"}
        for invalid in [{}, {"_id": 3}, {"_id": "x"}]:
            with pytest.raises(package.ResponseValidationError):
                invoke(
                    package,
                    lambda client: client.create_item(body),
                    lambda _, invalid=invalid: httpx.Response(200, json=invalid),
                )
    shape["properties"]["field_id"] = {"type": "string"}
    with (
        pytest.raises(GenerationError, match="property names collide"),
        generated(tmp_path / "collision", paths, {"Item": shape}),
    ):
        pass


@pytest.mark.parametrize(
    "wire,python_name",
    [
        ("model_dump", "field_model_dump"),
        ("model_validate", "field_model_validate"),
        ("_id", "field_id"),
    ],
)
def test_021_query_fields_are_public_and_validated(tmp_path, wire, python_name):
    paths = {
        "/item": {
            "get": {
                "operationId": "getItem",
                "parameters": [
                    {
                        "name": wire,
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "minLength": 3},
                    }
                ],
                "responses": {"204": {}},
            }
        }
    }
    with generated(tmp_path, paths) as package:
        seen, _ = invoke(
            package, lambda client: client.get_item(**{python_name: "valid"})
        )
        assert seen[0].url.params[wire] == "valid"
        query_model = importlib.import_module("ticket_api.models").GetItemParams
        assert python_name in query_model.model_fields
        with pytest.raises(package.RequestValidationError):
            invoke(package, lambda client: client.get_item(**{python_name: "x"}))
        with pytest.raises(TypeError):
            invoke(package, lambda client: client.get_item())


def test_020_content_type_control_argument_is_reserved_for_variants(tmp_path):
    content = {
        "application/json": {"schema": {"type": "string"}},
        "text/plain": {"schema": {"type": "string"}},
    }
    paths = {
        "/item": {
            "post": {
                "operationId": "createItem",
                "parameters": [
                    {
                        "name": "content_type",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "requestBody": {"required": True, "content": content},
                "responses": {"204": {}},
            }
        }
    }
    with (
        pytest.raises(GenerationError, match="generated content_type"),
        generated(tmp_path, paths),
    ):
        pass
    assert not (tmp_path / "ticket_api").exists()
    del content["text/plain"]
    with generated(tmp_path, paths) as package:
        seen, _ = invoke(
            package,
            lambda client: client.create_item(content_type="wire", body="value"),
        )
        assert seen[0].url.params["content_type"] == "wire"


@pytest.mark.parametrize("name", ["__init__", "stream_download", "streamDownload"])
def test_019_generated_method_collisions_fail_before_writes(tmp_path, name):
    paths = {"/other": {"get": {"operationId": name, "responses": {"204": {}}}}}
    if name != "__init__":
        paths["/download"] = {
            "get": {
                "operationId": "download",
                "responses": {"200": {"content": {"application/octet-stream": {}}}},
            }
        }
    with (
        pytest.raises(GenerationError, match="generated client methods"),
        generated(tmp_path, paths),
    ):
        pass
    assert not (tmp_path / "ticket_api").exists()


@pytest.mark.parametrize(
    "wire,python_name",
    [
        ("kindType", "kind_type"),
        ("type-name", "type_name"),
        ("class", "class_"),
        ("model_type", "model_type_"),
        ("type", "type"),
    ],
)
def test_018_discriminator_field_aliases(tmp_path, wire, python_name):
    schemas = {
        name: {
            "type": "object",
            "required": [wire],
            "properties": {wire: {"type": "string", "const": name.lower()}},
        }
        for name in ["A", "B"]
    }
    schemas["Choice"] = {
        "oneOf": [{"$ref": f"#/components/schemas/{name}"} for name in ["A", "B"]],
        "discriminator": {
            "propertyName": wire,
            "mapping": {
                name.lower(): f"#/components/schemas/{name}" for name in ["A", "B"]
            },
        },
    }
    paths = {
        "/item": {
            "post": {
                "operationId": "createItem",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Choice"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Choice"}
                            }
                        }
                    }
                },
            }
        }
    }
    with generated(tmp_path, paths, schemas) as package:
        body = package.A(**{python_name: "a"})
        seen, result = invoke(
            package,
            lambda client: client.create_item(body),
            lambda _: httpx.Response(200, json={wire: "b"}),
        )
        assert isinstance(result, package.B)
        assert getattr(result, python_name) == "b"
        assert json.loads(seen[0].content) == {wire: "a"}


def test_017_discriminator_enums_follow_shared_variants(tmp_path):
    variants = {
        name: {
            "type": "object",
            "required": ["kind"],
            "properties": {"kind": {"type": "string", "const": name.lower()}},
        }
        for name in ["A", "B", "C"]
    }
    variants["Choice"] = {
        "oneOf": [{"$ref": f"#/components/schemas/{name}"} for name in ["A", "B"]],
        "discriminator": {
            "propertyName": "kind",
            "mapping": {
                name.lower(): f"#/components/schemas/{name}" for name in ["A", "B"]
            },
        },
    }
    variants["OtherChoice"] = {
        "oneOf": [{"$ref": f"#/components/schemas/{name}"} for name in ["A", "C"]],
        "discriminator": {
            "propertyName": "kind",
            "mapping": {
                name.lower(): f"#/components/schemas/{name}" for name in ["A", "C"]
            },
        },
    }
    paths = {
        f"/{tag}/{name}": {
            "get": {
                "operationId": f"get{name}",
                "tags": [tag],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{name}"}
                            }
                        }
                    }
                },
            }
        }
        for tag, name in [("one", "Choice"), ("two", "A"), ("two", "OtherChoice")]
    }
    with generated(tmp_path, paths, variants, tags=["one", "two"]) as package:
        from pydantic import TypeAdapter

        assert isinstance(
            TypeAdapter(package.Choice).validate_python({"kind": "a"}), package.A
        )
        assert isinstance(
            TypeAdapter(package.OtherChoice).validate_python({"kind": "a"}), package.A
        )
        for client_name, method in [
            ("OneClient", "get_choice"),
            ("TwoClient", "get_a"),
        ]:
            _, result = invoke(
                package,
                lambda client, method=method: getattr(client, method)(),
                lambda _: httpx.Response(200, json={"kind": "a"}),
                client_name=client_name,
            )
            assert isinstance(result, package.A)


@pytest.mark.parametrize("tags", [[], ["one"], ["one", "two"]])
@pytest.mark.parametrize("override", [False, True])
def test_016_referenced_path_items_retain_parameters_and_tags(tmp_path, tags, override):
    parameter = {
        "name": "id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }
    item = {
        "parameters": [parameter],
        "get": {
            "operationId": "getItem",
            "tags": ["one", "two"],
            "responses": {
                "200": {"content": {"application/json": {"schema": {"type": "string"}}}}
            },
        },
    }
    path = {"$ref": "#/components/pathItems/Item"}
    if override:
        path["parameters"] = [
            parameter,
            {"name": "q", "in": "query", "schema": {"type": "string"}},
        ]
    paths = {"/x/{id}": path}
    components = {"pathItems": {"Item": item}}
    with generated(tmp_path, paths, tags=tags, components=components) as package:
        kwargs = {"q": "authored"} if override else {}
        seen, result = invoke(
            package,
            lambda client: client.get_item("value", **kwargs),
            lambda _: httpx.Response(200, json="ok"),
            client_name="OneClient" if len(tags) > 1 else "TicketApiClient",
        )
        assert seen[0].url.path == "/x/value"
        assert result == "ok"
        if override:
            assert seen[0].url.params["q"] == "authored"
    components["pathItems"]["Item"] = {"$ref": "#/components/pathItems/Item"}
    with (
        pytest.raises(GenerationError, match="cyclic Path Item"),
        generated(tmp_path / "cycle", paths, tags=tags, components=components),
    ):
        pass


@pytest.mark.parametrize("tags", [["one"], ["one", "two"]])
def test_015_tag_selection_follows_reusable_components(tmp_path, tags):
    components = {
        "schemas": {
            "RawThing": {
                "title": "Thing",
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "string"},
                    "next": {"$ref": "#/components/schemas/RawThing"},
                },
            },
            "Unused": {"type": "string"},
        },
        "parameters": {
            "Limit": {"name": "limit", "in": "query", "schema": {"type": "integer"}}
        },
        "headers": {"Count": {"schema": {"type": "integer"}}},
        "requestBodies": {
            "Input": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/RawThing"}
                    }
                },
            }
        },
        "responses": {
            "Ok": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/RawThing"}
                    }
                },
                "headers": {"X-Count": {"$ref": "#/components/headers/Count"}},
            },
            "Unused": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Unused"}
                    }
                }
            },
        },
    }
    paths = {
        f"/{tag}": {
            "post": {
                "operationId": f"create{tag.title()}",
                "tags": [tag],
                "parameters": [{"$ref": "#/components/parameters/Limit"}],
                "requestBody": {"$ref": "#/components/requestBodies/Input"},
                "responses": {"200": {"$ref": "#/components/responses/Ok"}},
            }
        }
        for tag in ["one", "two"]
    }
    with generated(tmp_path, paths, tags=tags, components=components) as package:
        client_name = "TicketApiClient" if len(tags) == 1 else "OneClient"
        seen, result = invoke(
            package,
            lambda client: client.create_one(body=package.Thing(id="request"), limit=2),
            lambda _: httpx.Response(
                200, json={"id": "response"}, headers={"X-Count": "3"}
            ),
            client_name=client_name,
        )
        assert result.body.id == "response"
        assert result.x_count == 3
        assert json.loads(seen[0].content) == {"id": "request"}
        assert not hasattr(package, "Unused")


@pytest.mark.parametrize("value", ["word", 7])
def test_014_inline_oneof_imports_and_runtime(tmp_path, value):
    one_of = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
    paths = {
        "/item/{id}": {
            "put": {
                "operationId": "putItem",
                "parameters": [
                    {"name": name, "in": location, "required": True, "schema": one_of}
                    for name, location in [
                        ("id", "path"),
                        ("q", "query"),
                        ("X-Value", "header"),
                    ]
                ],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": one_of}},
                },
                "responses": {
                    "200": {"content": {"application/json": {"schema": one_of}}}
                },
            }
        }
    }
    with generated(tmp_path, paths) as package:
        seen, result = invoke(
            package,
            lambda client: client.put_item(
                id=value, q=value, x__value=value, body=value
            ),
            lambda _: httpx.Response(200, json=value),
        )
        assert result == value
        assert json.loads(seen[0].content) == value
        assert seen[0].url.params["q"] == str(value)


@pytest.mark.parametrize("version", ["3.0.3", "3.1.0"])
def test_013_nullable_component_references(tmp_path, version):
    thing = {
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "integer", "minimum": 1}},
    }
    if version.startswith("3.0"):
        thing["nullable"] = True
    else:
        thing["type"] = ["object", "null"]
    schemas = {
        "Thing": thing,
        "MaybeThing": {"$ref": "#/components/schemas/Thing"},
        "Parent": {
            "type": "object",
            "required": ["thing"],
            "properties": {"thing": {"$ref": "#/components/schemas/Thing"}},
        },
    }
    paths = {
        "/item": {
            "put": {
                "operationId": "putItem",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/MaybeThing"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Thing"}
                            }
                        }
                    }
                },
            }
        }
    }
    with generated(tmp_path, paths, schemas, openapi=version) as package:
        assert package.Parent.model_validate({"thing": None}).thing is None
        seen, result = invoke(
            package,
            lambda client: client.put_item(None),
            lambda _: httpx.Response(
                200, content=b"null", headers={"Content-Type": "application/json"}
            ),
        )
        assert result is None
        assert seen[0].content == b"null"
        body = package.Thing(id=1)
        _, result = invoke(
            package,
            lambda client: client.put_item(body),
            lambda _: httpx.Response(200, json={"id": 1}),
        )
        assert result.id == 1
        for invalid in [{}, {"id": 0}]:
            with pytest.raises(package.ResponseValidationError):
                invoke(
                    package,
                    lambda client: client.put_item(body),
                    lambda _, invalid=invalid: httpx.Response(200, json=invalid),
                )

    if version.startswith("3.0"):
        del thing["type"]
        with (
            generated(tmp_path / "untyped", paths, schemas, openapi=version) as package,
            pytest.raises(package.ResponseValidationError),
        ):
            invoke(
                package,
                lambda client: client.put_item(package.Thing(id=1)),
                lambda _: httpx.Response(
                    200,
                    content=b"null",
                    headers={"Content-Type": "application/json"},
                ),
            )


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
def generated(
    tmp_path, paths, schemas=None, *, http_client="protocol", tags=(), **spec_options
):
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "info": {"title": "Ticket regressions", "version": "1"},
            "paths": paths,
            "components": {"schemas": schemas or {}},
            **spec_options,
        }
    )
    if len(tags) == 1:
        spec = filter_operations_by_tags(spec, tags)
    write_client(
        spec=spec,
        package_dir=tmp_path / "ticket_api",
        package_name="ticket_api",
        http_client=http_client,
        tags=tags,
    )
    sys.path.insert(0, str(tmp_path))
    try:
        yield importlib.import_module("ticket_api")
    finally:
        sys.path.remove(str(tmp_path))
        for name in list(sys.modules):
            if name == "ticket_api" or name.startswith("ticket_api."):
                del sys.modules[name]


def invoke(
    package,
    action,
    handler=None,
    headers=None,
    client_name="TicketApiClient",
    credentials=None,
):
    seen = []

    def capture(request):
        seen.append(request)
        return handler(request) if handler else httpx.Response(204)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(capture)
        ) as transport:
            client = getattr(package, client_name)(
                transport,
                "https://example.test",
                headers=headers,
                credentials=credentials,
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
