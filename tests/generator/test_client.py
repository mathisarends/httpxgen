from httpxgen.generator.client import render_client
from httpxgen.generator.operations import Operation, Parameter, Response
from httpxgen.openapi import HttpMethod


def test_render_client_handles_an_api_without_operations():
    source = render_client((), {}, "EmptyClient")

    assert "class EmptyClient:" in source
    assert "client: httpx.AsyncClient" in source
    assert "self._client = client" in source
    assert "async def __aenter__(self) -> Self:" in source
    assert "httpx.AsyncClient()" not in source
    assert source.rstrip().endswith("pass")


def test_render_client_renders_parameters_and_response_branches():
    operation = Operation(
        method=HttpMethod.GET,
        path="/charges/{chargeId}",
        name="get_charge",
        parameters=(
            Parameter("charge_id", "chargeId", "path", "str", True),
            Parameter("status", "status", "query", "str | None", False),
            Parameter("page_size", "page-size", "query", "int | None", False),
            Parameter("trace_id", "trace-id", "header", "str", True),
        ),
        body_annotation=None,
        body_required=False,
        responses=(
            Response(status=200, annotation="Charge", model_annotation="Charge"),
            Response(status=204, annotation="None", model_annotation=None),
        ),
    )

    source = render_client((operation,), {"Charge": {"type": "object"}}, "Client")

    assert "class _HttpMethod(StrEnum):" in source
    assert 'GET = "GET"' in source
    assert "from .models import Charge, GetChargeParams" in source
    assert "params = GetChargeParams(" in source
    assert "status=status," in source
    assert "page_size=page_size," in source
    assert "path.replace('{chargeId}', _serialize_path(" in source
    assert 'url=f"{self._base_url}{path}"' in source
    assert "method=_HttpMethod.GET" in source
    assert "query.extend(_serialize_query('status'" in source
    assert "headers['trace-id'] = _serialize_simple(trace_id" in source
    assert "if response.status_code == 200:" in source
    assert "return Charge.model_validate(response.json())" in source
    assert "if response.status_code == 204:" in source
    assert "return None" in source


def test_render_client_does_not_create_params_for_an_operation_without_queries():
    operation = Operation(
        method=HttpMethod.POST,
        path="/charges",
        name="create_charge",
        parameters=(),
        body_annotation="CreateChargeRequest",
        body_required=True,
        responses=(Response(201, "Charge", "Charge"),),
    )

    source = render_client(
        (operation,),
        {
            "Charge": {"type": "object"},
            "CreateChargeRequest": {"type": "object"},
        },
        "Client",
    )

    assert "CreateChargeParams" not in source
    assert "params=" not in source
    assert "if body is not None" not in source
    assert "body_arguments['json'] = TypeAdapter(CreateChargeRequest).dump_python(" in source


def test_render_client_guards_optional_request_body_serialization():
    operation = Operation(
        method=HttpMethod.PATCH,
        path="/charges/{chargeId}",
        name="update_charge",
        parameters=(Parameter("charge_id", "chargeId", "path", "str", True),),
        body_annotation="UpdateCharge",
        body_required=False,
        responses=(Response(200, "Charge", "Charge"),),
    )

    source = render_client(
        (operation,),
        {
            "Charge": {"type": "object"},
            "UpdateCharge": {"type": "object"},
        },
        "Client",
    )

    assert "if body is not None" in source
    assert "body_arguments: dict[str, Any] = {}" in source
