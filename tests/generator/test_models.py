import pytest

from httpxgen.generator import GenerationError
from httpxgen.generator.models import exported_model_names, render_models


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
    assert "status: Status | None = None" in source


def test_render_models_rejects_non_string_component_enums():
    with pytest.raises(GenerationError, match="only string component enums"):
        render_models({"Status": {"enum": [1, 2]}})


def test_exported_model_names_include_generated_discriminator_enums(
    generatable_spec,
):
    names = exported_model_names(generatable_spec.components.schemas)

    assert "PaymentMethodType" in names
    assert "PaymentMethod" in names
