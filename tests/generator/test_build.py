import importlib
import sys

import pytest

from httpxgen import OpenAPISpec, write_client
from httpxgen.generator import GenerationError, generate_client, generate_workspace


def test_generate_client_produces_a_complete_package(generatable_spec):
    files = generate_client(generatable_spec, "payments")

    assert set(files) == {
        "client.py",
        "serialization.py",
        "models.py",
        "exceptions.py",
        "http_methods.py",
        "__init__.py",
        "py.typed",
    }
    assert files["client.py"].startswith("# ")
    assert "class PaymentsClient" in files["client.py"]
    assert "class PaymentMethodType(StrEnum)" in files["models.py"]
    assert "class HttpMethods(StrEnum):" in files["http_methods.py"]
    assert "method=HttpMethods.POST" in files["client.py"]
    assert files["py.typed"] == ""


def test_generate_client_keeps_shared_runtime_out_of_the_client_module(
    generatable_spec,
):
    files = generate_client(generatable_spec, "payments")

    assert "class PaymentsClient:" in files["client.py"]
    assert "def serialize_path" not in files["client.py"]
    assert "def apply_security" not in files["client.py"]
    assert "def serialize_path" in files["serialization.py"]
    assert "def apply_security" in files["serialization.py"]
    assert (
        '"bearerAuth": SecurityScheme("bearer", "header", "Authorization"'
        in (files["serialization.py"])
    )


def test_generate_client_rejects_non_json_request_bodies():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/avatars": {
                    "put": {
                        "operationId": "uploadAvatar",
                        "requestBody": {
                            "required": True,
                            "content": {"image/png": {"schema": {"type": "string"}}},
                        },
                        "responses": {"204": {}},
                    }
                }
            },
        }
    )

    with pytest.raises(GenerationError, match="unsupported request body media type"):
        generate_client(spec, "avatars")


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


def test_generated_one_of_requires_exactly_one_matching_variant(tmp_path):
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {},
            "components": {
                "schemas": {
                    "ByName": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {"name": {"type": "string"}},
                    },
                    "ById": {
                        "type": "object",
                        "required": ["id"],
                        "properties": {"id": {"type": "integer"}},
                    },
                    "Lookup": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/ByName"},
                            {"$ref": "#/components/schemas/ById"},
                        ]
                    },
                }
            },
        }
    )

    write_client(spec=spec, package_dir=tmp_path / "lookup", package_name="lookup")

    sys.path.insert(0, str(tmp_path))
    try:
        package = importlib.import_module("lookup")
        from pydantic import TypeAdapter, ValidationError

        adapter = TypeAdapter(package.Lookup)
        assert adapter.validate_python({"name": "Ada"}).name == "Ada"
        with pytest.raises(ValidationError, match="matched 2"):
            adapter.validate_python({"name": "Ada", "id": 1})
        with pytest.raises(ValidationError, match="matched 0"):
            adapter.validate_python({"active": True})
    finally:
        sys.path.remove(str(tmp_path))
        for module_name in [
            name
            for name in sys.modules
            if name == "lookup" or name.startswith("lookup.")
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


def test_generate_workspace_shares_support_modules_between_tag_packages(
    generatable_spec,
):
    files = generate_workspace(generatable_spec, ["payments", "invoices"], "api")

    assert set(files) == {
        "__init__.py",
        "py.typed",
        "shared/__init__.py",
        "shared/exceptions.py",
        "shared/http_methods.py",
        "shared/serialization.py",
        "shared/models.py",
        "payments/__init__.py",
        "payments/client.py",
        "payments/models.py",
        "invoices/__init__.py",
        "invoices/client.py",
        "invoices/models.py",
    }
    assert "class ApiError(Exception):" in files["shared/exceptions.py"]
    assert "class HttpMethods(StrEnum):" in files["shared/http_methods.py"]
    assert 'POST = "POST"' in files["shared/http_methods.py"]
    assert "def apply_security(" in files["shared/serialization.py"]
    assert "class Money(BaseModel):" in files["shared/models.py"]
    assert "class Charge(BaseEntity, AuditInfo):" in files["payments/models.py"]
    assert "class Invoice(BaseEntity):" in files["invoices/models.py"]
    assert "class Charge" not in files["invoices/models.py"]
    for tag in ("payments", "invoices"):
        client = files[f"{tag}/client.py"]
        assert "    ApiError," in client
        assert "    HttpMethods," in client
        assert "method=HttpMethods." in client
        assert 'method="' not in client
        assert f"from api.{tag}.models import" in client
        assert "class ApiError(Exception):" not in client
        assert "def apply_security(" not in client
    assert "from .invoices import InvoicesClient" in files["__init__.py"]
    assert "from .payments import PaymentsClient" in files["__init__.py"]
    assert "from .shared import ApiError" in files["__init__.py"]


def _two_tag_spec(first_operation_id: str, second_operation_id: str) -> OpenAPISpec:
    def operation(operation_id: str, tag: str) -> dict:
        return {
            "operationId": operation_id,
            "tags": [tag],
            "responses": {
                "200": {
                    "description": "ok",
                    "headers": {"X-Request-Id": {"schema": {"type": "string"}}},
                    "content": {"application/json": {"schema": {"type": "string"}}},
                }
            },
        }

    return OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/a": {"get": operation(first_operation_id, "alpha")},
                "/b": {"get": operation(second_operation_id, "beta")},
            },
        }
    )


def test_generate_workspace_rejects_response_models_colliding_across_tags():
    spec = _two_tag_spec("getThing", "get_thing")

    with pytest.raises(GenerationError) as error:
        generate_workspace(spec, ["alpha", "beta"], "api")

    assert "GetThingResult200" in str(error.value)
    assert "collide across the workspace" in str(error.value)


def test_generate_workspace_allows_distinct_response_models_per_tag():
    spec = _two_tag_spec("getThing", "getOther")

    files = generate_workspace(spec, ["alpha", "beta"], "api")

    assert "class GetThingResult200(BaseModel):" in files["alpha/models.py"]
    assert "class GetOtherResult200(BaseModel):" in files["beta/models.py"]


def test_generate_workspace_allows_one_operation_shared_by_several_tags():
    spec = OpenAPISpec.model_validate(
        {
            "openapi": "3.1.0",
            "paths": {
                "/a": {
                    "get": {
                        "operationId": "getThing",
                        "tags": ["alpha", "beta"],
                        "responses": {
                            "200": {
                                "description": "ok",
                                "headers": {
                                    "X-Request-Id": {"schema": {"type": "string"}}
                                },
                                "content": {
                                    "application/json": {"schema": {"type": "string"}}
                                },
                            }
                        },
                    }
                }
            },
        }
    )

    files = generate_workspace(spec, ["alpha", "beta"], "api")

    assert "class GetThingResult200(BaseModel):" in files["alpha/models.py"]
    assert "class GetThingResult200(BaseModel):" in files["beta/models.py"]
