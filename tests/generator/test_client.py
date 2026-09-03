from httpxgen.generator.client import render_client
from httpxgen.generator.operations import Operation, Parameter, Response
from httpxgen.openapi import HttpMethod


def test_render_client_handles_an_api_without_operations():
    source = render_client((), {}, "EmptyClient")

    assert "class EmptyClient:" in source
    assert source.rstrip().endswith("pass")


def test_render_client_renders_parameters_and_response_branches():
    operation = Operation(
        method=HttpMethod.GET,
        path="/charges/{chargeId}",
        name="get_charge",
        parameters=(
            Parameter("charge_id", "chargeId", "path", "str", True),
            Parameter("status", "status", "query", "str | None", False),
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

    assert 'path = f"/charges/{charge_id}"' in source
    assert 'params["status"] = status' in source
    assert 'headers["trace-id"] = trace_id' in source
    assert "if response.status_code == 200:" in source
    assert "return Charge.model_validate(response.json())" in source
    assert "if response.status_code == 204:" in source
    assert "return None" in source
