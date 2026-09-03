from collections.abc import Mapping
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.models import (
    class_name,
    discriminator_enums,
    ordered_schemas,
    string_literal,
)
from httpxgen.generator.templates import TemplateName, render_template

_RESERVED_NAMES = {"ApiError"}


def generate_package_init(schemas: Mapping[str, Any], client_name: str) -> str:
    discriminator_names = [
        enum.name for enum in dict.fromkeys(discriminator_enums(schemas).values())
    ]
    exported_models = [
        *discriminator_names,
        *(class_name(name) for name in ordered_schemas(schemas)),
    ]
    _check_no_name_collisions(exported_models, client_name)
    model_names = ",\n    ".join(exported_models)
    imports = f"\n    {model_names},\n" if model_names else ""
    exports = "\n".join(
        f"    {string_literal(name)}," for name in ["ApiError", client_name, *exported_models]
    )
    return render_template(
        TemplateName.PACKAGE_INIT,
        client_name=client_name,
        model_imports=imports,
        exports=exports,
    )


def _check_no_name_collisions(exported_models: list[str], client_name: str) -> None:
    reserved = {*_RESERVED_NAMES, client_name}
    conflicts = sorted(reserved.intersection(exported_models))
    if conflicts:
        names = ", ".join(conflicts)
        raise GenerationError(
            f"component schema name(s) {names} conflict with a generated symbol; "
            "rename the schema(s) in the OpenAPI document"
        )
    duplicates = sorted({name for name in exported_models if exported_models.count(name) > 1})
    if duplicates:
        raise GenerationError(
            f"multiple component schemas map to the same class name: {', '.join(duplicates)}"
        )
