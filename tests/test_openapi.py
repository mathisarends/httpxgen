import pytest
from pydantic import ValidationError

from httpxgen.openapi import HttpMethod, OpenAPISpec, get_operation


def test_openapi_3_document_is_parsed_with_aliases():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/charges": {
                    "post": {
                        "operationId": "createCharge",
                        "responses": {},
                    }
                }
            },
        }
    )

    operation = get_operation(spec.paths["/charges"], HttpMethod.POST)

    assert operation is not None
    assert operation.operation_id == "createCharge"


@pytest.mark.parametrize("version", ["2.0", "3.2.0", "3.latest"])
def test_unsupported_openapi_document_is_rejected(version):
    with pytest.raises(ValidationError, match="only OpenAPI 3.0 and 3.1"):
        OpenAPISpec.model_validate({"openapi": version, "paths": {}})
