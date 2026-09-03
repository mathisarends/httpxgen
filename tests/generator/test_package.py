import pytest

from httpxgen.generator import GenerationError
from httpxgen.generator.package import render_package_init


def test_render_package_init_exports_the_client_error_and_models():
    source = render_package_init({"Charge": {"type": "object"}}, "PaymentsClient")

    assert "from .client import PaymentsClient" in source
    assert "from .exceptions import ApiError" in source
    assert "from .models import (\n    Charge," in source
    assert '    "PaymentsClient",' in source
    assert '    "Charge",' in source


@pytest.mark.parametrize("schema_name", ["ApiError", "PaymentsClient"])
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
