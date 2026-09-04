from pathlib import Path

import pytest
import yaml

from httpxgen import OpenAPISpec

_SPEC_PATH = Path(__file__).parent.parent / "specs" / "api.yml"


@pytest.fixture
def reference_spec() -> OpenAPISpec:
    return _read_reference_spec()


@pytest.fixture
def generatable_spec() -> OpenAPISpec:
    return _read_reference_spec(rename_api_error=True)


def _read_reference_spec(*, rename_api_error: bool = False) -> OpenAPISpec:
    source = _SPEC_PATH.read_text()
    if rename_api_error:
        source = source.replace("ApiError", "PaymentApiError")
    return OpenAPISpec.model_validate(yaml.safe_load(source))
