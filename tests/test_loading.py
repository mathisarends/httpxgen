import json

import pytest

from httpxgen.generator import GenerationError
from httpxgen.loading import load_openapi


def test_load_openapi_reads_a_json_document(tmp_path):
    path = tmp_path / "openapi.json"
    path.write_text(json.dumps({"openapi": "3.1.0", "paths": {}}))

    spec = load_openapi(path)

    assert spec.openapi == "3.1.0"


@pytest.mark.parametrize("document", [[], "openapi", None])
def test_load_openapi_rejects_non_object_documents(tmp_path, document):
    path = tmp_path / "openapi.json"
    path.write_text(json.dumps(document))

    with pytest.raises(GenerationError, match="must be an object"):
        load_openapi(path)


def test_load_openapi_reads_yaml(tmp_path):
    path = tmp_path / "openapi.yaml"
    path.write_text("openapi: 3.1.0\npaths: {}\n")

    assert load_openapi(path).openapi == "3.1.0"


def test_load_openapi_reports_validation_errors(tmp_path):
    path = tmp_path / "openapi.json"
    path.write_text(json.dumps({"openapi": "2.0", "paths": {}}))

    with pytest.raises(GenerationError, match="invalid OpenAPI document"):
        load_openapi(path)
