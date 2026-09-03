import importlib
import sys

import pytest

from httpxgen import OpenAPISpec, write_client
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


def test_generate_client_supports_recursive_and_mapped_discriminator_models(tmp_path):
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {},
            "components": {
                "schemas": {
                    "Node": {
                        "type": "object",
                        "properties": {
                            "children": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Node"},
                            }
                        },
                    },
                    "Cat": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                    "Pet": {
                        "oneOf": [{"$ref": "#/components/schemas/Cat"}],
                        "discriminator": {
                            "propertyName": "kind",
                            "mapping": {"feline": "#/components/schemas/Cat"},
                        },
                    },
                }
            },
        }
    )

    write_client(
        spec=spec, package_dir=tmp_path / "recursive", package_name="recursive"
    )
    source = (tmp_path / "recursive" / "models.py").read_text()

    assert "children: list[Node] = None" in source
    assert "kind: Literal[PetKind.FELINE]" in source
    sys.path.insert(0, str(tmp_path))
    try:
        package = importlib.import_module("recursive")
        node = package.Node.model_validate({"children": [{"children": []}]})
        assert node.children[0].children == []
        cat = package.Cat.model_validate({"kind": "feline", "name": "Minka"})
        assert cat.kind == "feline"
    finally:
        sys.path.remove(str(tmp_path))
        for module_name in [
            name
            for name in sys.modules
            if name == "recursive" or name.startswith("recursive.")
        ]:
            del sys.modules[module_name]


def test_generate_client_rejects_an_unresolved_schema_reference():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {},
            "components": {"schemas": {"A": {"$ref": "#/components/schemas/Missing"}}},
        }
    )

    with pytest.raises(GenerationError, match="unresolved reference"):
        generate_client(spec, "broken")


def test_generate_client_rejects_generated_namespace_collisions():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "get": {
                        "operationId": "listItems",
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "schema": {"type": "integer"},
                            }
                        ],
                        "responses": {"204": {}},
                    }
                }
            },
            "components": {"schemas": {"ListItemsParams": {"type": "object"}}},
        }
    )

    with pytest.raises(GenerationError, match="ListItemsParams"):
        generate_client(spec, "collision")


def test_generate_client_rejects_operation_names_reserved_by_the_client():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/close": {"post": {"operationId": "aclose", "responses": {"204": {}}}}
            },
        }
    )

    with pytest.raises(GenerationError, match="client methods"):
        generate_client(spec, "collision")
