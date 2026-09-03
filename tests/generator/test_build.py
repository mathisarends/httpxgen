import pytest

from httpxgen.generator import GenerationError, generate_client


def test_generate_client_produces_a_complete_package(generatable_spec):
    files = generate_client(generatable_spec, "payments")

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


def test_generate_client_supports_binary_request_bodies(reference_spec):
    files = generate_client(reference_spec, "payments")

    assert "body: bytes" in files["client.py"]
    assert "body_arguments['content'] = body" in files["client.py"]


def test_generate_client_renames_an_api_error_schema(reference_spec):
    files = generate_client(reference_spec, "payments")

    assert "class ApiErrorModel(BaseModel):" in files["models.py"]
    assert "ApiErrorModel.model_validate" in files["client.py"]
