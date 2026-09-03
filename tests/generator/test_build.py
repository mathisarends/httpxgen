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


def test_generate_client_rejects_non_json_request_bodies(reference_spec):
    reference_spec.components.schemas.pop("ApiError")

    with pytest.raises(GenerationError, match="application/json"):
        generate_client(reference_spec, "payments")


def test_generate_client_rejects_model_names_reserved_by_the_package(reference_spec):
    del reference_spec.paths["/customers/{customerId}/avatar"]

    with pytest.raises(GenerationError, match="ApiError"):
        generate_client(reference_spec, "payments")
