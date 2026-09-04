import pytest

from httpxgen.generator import GenerationError
from httpxgen.generator.package import (
    render_client_package_init,
    render_package_init,
    render_workspace_init,
)


def test_render_package_init_exports_the_client_error_and_models():
    source = render_package_init({"Charge": {"type": "object"}}, "PaymentsClient")

    assert "from .client import PaymentsClient" in source
    assert "from .exceptions import ApiError" in source
    assert "from .http_methods import HttpMethods" in source
    assert "from .models import Charge" in source
    assert '    "PaymentsClient",' in source
    assert '    "Charge",' in source
    assert '    "HttpMethods",' in source


@pytest.mark.parametrize(
    "schema_name", ["ApiError", "HttpMethods", "PaymentsClient"]
)
def test_render_package_init_rejects_reserved_model_names(schema_name):
    with pytest.raises(GenerationError, match=schema_name):
        render_package_init({schema_name: {"type": "object"}}, "PaymentsClient")


def test_render_package_init_rejects_normalized_name_collisions():
    schemas = {
        "payment-method": {"type": "object"},
        "payment_method": {"type": "object"},
    }

    with pytest.raises(GenerationError, match="same class name"):
        render_package_init(schemas, "PaymentsClient")


def test_render_client_package_init_exports_its_client_and_own_models():
    source = render_client_package_init("PaymentsClient", ["Charge"])

    assert "from .client import PaymentsClient" in source
    assert "from .models import Charge" in source
    assert "ApiError" not in source


def test_render_workspace_init_reexports_every_client_and_shared_model():
    source = render_workspace_init(
        [("payments", "PaymentsClient"), ("invoices", "InvoicesClient")],
        {"payments": ["Charge"], "invoices": ["Invoice"]},
        ["Money"],
    )

    assert "from .invoices import InvoicesClient" in source
    assert "from .invoices.models import Invoice" in source
    assert "from .payments import PaymentsClient" in source
    assert "from .payments.models import Charge" in source
    assert "from .shared import ApiError, HttpMethods" in source
    assert "from .shared.models import Money" in source
    assert '    "InvoicesClient",' in source
    assert '    "PaymentsClient",' in source
    assert '    "HttpMethods",' in source
