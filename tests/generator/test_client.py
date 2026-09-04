from httpxgen.generator.client import Layout, render_client, render_serialization
from httpxgen.generator.operations import (
    Body,
    Operation,
    Parameter,
    Response,
    SecurityScheme,
)
from httpxgen.openapi import HttpMethod

_LAYOUT = Layout(
    exceptions="payments.exceptions",
    serialization="payments.serialization",
    models="payments.models",
    http_methods="payments.http_methods",
)


def test_render_client_handles_an_api_without_operations():
    source = render_client((), {}, "EmptyClient", _LAYOUT)

    assert "class EmptyClient:" in source
    assert "client: httpx.AsyncClient" in source
    assert "self._client = client" in source
    assert "async def __aenter__(self) -> Self:" in source
    assert "def serialize_path" not in source


def test_render_client_imports_shared_support_from_the_workspace_package():
    operation = Operation(
        method=HttpMethod.GET,
        path="/items/{itemId}",
        name="get_item",
        parameters=(
            Parameter("item_id", "itemId", "path", "str", True, "simple", False),
        ),
        body_annotation=None,
        body_required=False,
        responses=(Response(204, "None", None),),
    )

    layout = Layout(
        exceptions="api.shared",
        serialization="api.shared",
        models="api.items.models",
        http_methods="api.shared",
        shared_models="api.shared.models",
        shared_names=frozenset({"Money"}),
    )

    source = render_client((operation,), {}, "ItemsClient", layout)

    assert "from api.shared import ApiError, HttpMethods, serialize_path" in source
    assert "from payments." not in source


def test_render_client_renders_parameters_and_response_branches():
    operation = Operation(
        method=HttpMethod.GET,
        path="/charges/{chargeId}",
        name="get_charge",
        parameters=(
            Parameter("charge_id", "chargeId", "path", "str", True, "simple", False),
            Parameter("status", "status", "query", "str | None", False),
            Parameter("page_size", "page-size", "query", "int | None", False),
            Parameter("trace_id", "trace-id", "header", "str", True, "simple", False),
        ),
        body_annotation=None,
        body_required=False,
        responses=(
            Response(status=200, annotation="Charge", model_annotation="Charge"),
            Response(status=204, annotation="None", model_annotation=None),
        ),
    )

    source = render_client(
        (operation,), {"Charge": {"type": "object"}}, "Client", _LAYOUT
    )

    assert "method=HttpMethods.GET" in source
    assert 'method="GET"' not in source
    assert "from payments.models import Charge, GetChargeParams" in source
    assert "params = GetChargeParams(" in source
    assert "status=status," in source
    assert "page_size=page_size," in source
    assert (
        'path = path.replace("{chargeId}", serialize_path("chargeId", charge_id))'
        in (source)
    )
    assert 'url=f"{self._base_url}{path}"' in source
    assert 'query.extend(serialize_query("status", params.status))' in source
    assert 'headers["trace-id"] = serialize_simple(trace_id)' in source
    assert "if response.status_code == 200:" in source
    assert "return Charge.model_validate(response.json())" in source
    assert "if response.status_code == 204:" in source
    assert "return None" in source


def test_render_client_renders_non_default_parameter_styles():
    operation = Operation(
        method=HttpMethod.GET,
        path="/items",
        name="list_items",
        parameters=(
            Parameter(
                "filter",
                "filter",
                "query",
                "dict[str, str] | None",
                False,
                style="deepObject",
            ),
            Parameter("tag", "tag", "query", "list[str] | None", False, explode=False),
        ),
        body_annotation=None,
        body_required=False,
        responses=(Response(204, "None", None),),
    )

    source = render_client((operation,), {}, "Client", _LAYOUT)

    assert 'serialize_query("filter", params.filter, "deepObject")' in source
    assert 'serialize_query("tag", params.tag, explode=False)' in source


def test_render_client_does_not_create_params_for_an_operation_without_queries():
    operation = Operation(
        method=HttpMethod.POST,
        path="/charges",
        name="create_charge",
        parameters=(),
        body_annotation="CreateChargeRequest",
        body_required=True,
        body=Body("CreateChargeRequest", True),
        responses=(Response(201, "Charge", "Charge"),),
    )

    source = render_client(
        (operation,),
        {
            "Charge": {"type": "object"},
            "CreateChargeRequest": {"type": "object"},
        },
        "Client",
        _LAYOUT,
    )

    assert "CreateChargeParams" not in source
    assert "params=" not in source
    assert "if body is not None" not in source
    assert "json_body = TypeAdapter(CreateChargeRequest).dump_python(" in source
    assert "json=json_body," in source


def test_render_client_guards_optional_request_body_serialization():
    operation = Operation(
        method=HttpMethod.PATCH,
        path="/charges/{chargeId}",
        name="update_charge",
        parameters=(
            Parameter("charge_id", "chargeId", "path", "str", True, "simple", False),
        ),
        body_annotation="UpdateCharge",
        body_required=False,
        body=Body("UpdateCharge", False),
        responses=(Response(200, "Charge", "Charge"),),
    )

    source = render_client(
        (operation,),
        {
            "Charge": {"type": "object"},
            "UpdateCharge": {"type": "object"},
        },
        "Client",
        _LAYOUT,
    )

    assert "body: UpdateCharge | None = None" in source
    assert "body_arguments: dict[str, Any] = {}" in source
    assert "if body is not None:" in source
    assert "**body_arguments," in source


def test_render_serialization_renders_the_security_schemes():
    operation = Operation(
        method=HttpMethod.GET,
        path="/items",
        name="list_items",
        parameters=(),
        body_annotation=None,
        body_required=False,
        responses=(Response(204, "None", None),),
        security=(("apiKey",),),
        security_schemes=(SecurityScheme("apiKey", "apiKey", "query", "key"),),
    )

    source = render_serialization(operation.security_schemes)

    assert "SECURITY_SCHEMES: dict[str, SecurityScheme] = {" in source
    assert '"apiKey": SecurityScheme("apiKey", "query", "key", "")' in source
    assert "def serialize_query(" in source
    assert "class BaseClient" not in source


def test_render_serialization_without_security_schemes_is_still_complete():
    source = render_serialization(())

    assert "SECURITY_SCHEMES: dict[str, SecurityScheme] = {}" in source
    assert "def apply_security(" in source
