import sys
from pathlib import Path

import pytest
import yaml

from httpxgen import GenerationError, OpenAPISpec, generate_client, write_client

SPEC_PATH = Path(__file__).parent.parent / "specs" / "api.yaml"


def _load_spec(*, rename_api_error: bool = False) -> OpenAPISpec:
    text = SPEC_PATH.read_text()
    if rename_api_error:
        text = text.replace("ApiError", "PaymentApiError")
    return OpenAPISpec.model_validate(yaml.safe_load(text))


def _generatable_spec() -> OpenAPISpec:
    """The reference spec, minus the two edge cases that must raise on their own."""
    spec = _load_spec(rename_api_error=True)
    del spec.paths["/customers/{customerId}/avatar"]
    return spec


def test_non_json_request_bodies_are_rejected():
    with pytest.raises(GenerationError, match="application/json"):
        generate_client(_load_spec(rename_api_error=True), "payments")


def test_schema_name_colliding_with_generated_symbol_is_rejected():
    spec = _load_spec()
    del spec.paths["/customers/{customerId}/avatar"]
    with pytest.raises(GenerationError, match="ApiError"):
        generate_client(spec, "payments")


def test_generate_client_produces_expected_files():
    files = generate_client(_generatable_spec(), "payments")

    assert set(files) == {
        "client.py",
        "models.py",
        "exceptions.py",
        "__init__.py",
        "py.typed",
    }
    assert files["client.py"].startswith("# ")
    assert "class PaymentsClient" in files["client.py"]
    assert "class PaymentMethodType(StrEnum)" in files["models.py"]
    assert files["py.typed"] == ""


def test_generated_package_imports_and_runs(tmp_path):
    package_dir = tmp_path / "payments"
    write_client(
        spec=_generatable_spec(),
        package_dir=package_dir,
        package_name="payments",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        package = __import__("payments")
        client = package.PaymentsClient("https://payments.example.com/api")
        assert client._base_url == "https://payments.example.com/api"
        assert hasattr(client, "create_charge")
        assert hasattr(client, "list_charges")
        assert package.PaymentMethod is not None
    finally:
        sys.path.remove(str(tmp_path))
        for name in [n for n in sys.modules if n == "payments" or n.startswith("payments.")]:
            del sys.modules[name]


def test_write_client_check_mode(tmp_path):
    spec = _generatable_spec()
    package_dir = tmp_path / "payments"
    write_client(spec=spec, package_dir=package_dir, package_name="payments")

    write_client(spec=spec, package_dir=package_dir, package_name="payments", check=True)

    (package_dir / "client.py").write_text("# hand-edited, not generated\n")
    with pytest.raises(GenerationError):
        write_client(spec=spec, package_dir=package_dir, package_name="payments", check=True)
