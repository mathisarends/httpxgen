import pytest

from httpxgen.generator import GenerationError
from httpxgen.generator.models import exported_model_names, render_models
from httpxgen.generator.operations import Operation, Parameter, Response
from httpxgen.openapi import HttpMethod


def test_render_models_handles_an_api_without_component_schemas():
    source = render_models({})

    assert "# This API does not define component schemas." in source


def test_render_models_generates_enums_aliases_and_constrained_models():
    source = render_models(
        {
            "Status": {"type": "string", "enum": ["open", "closed"]},
            "Identifier": {"type": "string"},
            "Charge": {
                "type": "object",
                "additionalProperties": False,
                "required": ["charge-id"],
                "properties": {
                    "charge-id": {"type": "string", "minLength": 1},
                    "status": {"$ref": "#/components/schemas/Status"},
                },
            },
        }
    )

    assert "class Status(StrEnum):" in source
    assert "Identifier = str" in source
    assert "class Charge(BaseModel):" in source
    assert 'charge_id: str = Field(alias="charge-id", min_length=1)' in source
    assert "status: Status = None" in source


def test_render_models_supports_numeric_component_enums_as_literals():
    source = render_models({"Status": {"type": "integer", "enum": [1, 2]}})

    assert "Status = Literal[1, 2]" in source


def test_render_models_adds_exact_validation_only_to_one_of():
    source = render_models(
        {
            "TextOrNumber": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
            "LooseValue": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        }
    )

    assert "def _one_of(*variants: Any) -> BeforeValidator:" in source
    assert "TextOrNumber = Annotated[str | int, _one_of(str, int)]" in source
    assert "LooseValue = str | int" in source


def test_render_models_rejects_normalized_property_and_enum_collisions():
    with pytest.raises(GenerationError, match="property names collide"):
        render_models(
            {
                "Collision": {
                    "type": "object",
                    "properties": {"foo-bar": {}, "foo_bar": {}},
                }
            }
        )
    with pytest.raises(GenerationError, match="enum values collide"):
        render_models(
            {"Status": {"type": "string", "enum": ["in-progress", "in progress"]}}
        )


def test_render_models_supports_multiple_all_of_bases_and_typed_extras():
    source = render_models(
        {
            "Identity": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
            },
            "Audit": {
                "type": "object",
                "properties": {"created": {"type": "string"}},
            },
            "Entity": {
                "allOf": [
                    {"$ref": "#/components/schemas/Identity"},
                    {"$ref": "#/components/schemas/Audit"},
                    {
                        "type": "object",
                        "additionalProperties": {"type": "integer"},
                    },
                ]
            },
        }
    )

    assert "class Entity(Identity, Audit):" in source
    assert "__pydantic_extra__: dict[str, int] = Field(init=False)" in source


def test_render_models_generates_query_parameter_models():
    operation = Operation(
        method=HttpMethod.GET,
        path="/charges",
        name="list_charges",
        parameters=(
            Parameter("status", "status", "query", "str | None", False),
            Parameter("page_size", "page-size", "query", "int | None", False),
        ),
        body_annotation=None,
        body_required=False,
        responses=(Response(200, "None", None),),
    )

    source = render_models({}, (operation,))

    assert "class ListChargesParams(BaseModel):" in source
    assert "status: str | None = None" in source
    assert (
        'page_size: int | None = Field(None, serialization_alias="page-size")' in source
    )


def test_exported_model_names_include_generated_discriminator_enums(
    generatable_spec,
):
    names = exported_model_names(generatable_spec.components.schemas)

    assert "PaymentMethodType" in names
    assert "PaymentMethod" in names
