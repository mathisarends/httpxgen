from httpxgen.generator.naming import class_name, identifier
from httpxgen.generator.schema import ordered_schemas, schema_type


def test_python_names_are_derived_from_openapi_names():
    assert class_name("payment_method") == "PaymentMethod"
    assert class_name("3d-secure") == "Model3DSecure"
    assert identifier("listCharges") == "list_charges"
    assert identifier("class") == "class_"


def test_schema_type_translates_refs_collections_and_nullability():
    assert schema_type({"$ref": "#/components/schemas/PaymentMethod"}) == (
        "PaymentMethod"
    )
    assert schema_type({"type": "array", "items": {"type": "integer"}}) == ("list[int]")
    assert schema_type({"type": ["string", "null"]}) == "str | None"


def test_schemas_are_ordered_after_their_dependencies():
    schemas = {
        "Charge": {
            "type": "object",
            "properties": {"payment": {"$ref": "#/components/schemas/PaymentMethod"}},
        },
        "PaymentMethod": {"type": "string"},
    }

    assert ordered_schemas(schemas) == ["PaymentMethod", "Charge"]
