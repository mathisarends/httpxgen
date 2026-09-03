from collections.abc import Mapping
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.models import exported_model_names
from httpxgen.generator.naming import string_literal
from httpxgen.generator.operations import Operation, query_model_name, query_parameters
from httpxgen.generator.templates import TemplateName, render_template

_RESERVED_NAMES = {
    "Annotated",
    "Any",
    "ApiError",
    "ApiResponse",
    "BaseModel",
    "ConfigDict",
    "Field",
    "Literal",
    "StrEnum",
    "TypeAdapter",
    "UUID",
    "date",
    "datetime",
}
_CLIENT_METHODS = {"aclose", "__aenter__", "__aexit__"}


def validate_package_names(
    schemas: Mapping[str, Any], operations: tuple[Operation, ...], client_name: str
) -> None:
    exported_models = exported_model_names(schemas)
    query_models = [
        query_model_name(operation)
        for operation in operations
        if query_parameters(operation)
    ]
    generated_models = [*exported_models, *query_models]
    _check_no_name_collisions(generated_models, client_name)
    method_conflicts = sorted(
        _CLIENT_METHODS.intersection(operation.name for operation in operations)
    )
    if method_conflicts:
        raise GenerationError(
            "operationId values conflict with generated client methods: "
            + ", ".join(method_conflicts)
        )


def render_package_init(schemas: Mapping[str, Any], client_name: str) -> str:
    exported_models = sorted(exported_model_names(schemas))
    _check_no_name_collisions(exported_models, client_name)
    model_names = ",\n    ".join(exported_models)
    imports = f"\n    {model_names},\n" if model_names else ""
    exports = "\n".join(
        f"    {string_literal(name)},"
        for name in sorted(["ApiError", client_name, *exported_models])
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
    duplicates = sorted(
        {name for name in exported_models if exported_models.count(name) > 1}
    )
    if duplicates:
        raise GenerationError(
            f"multiple component schemas map to the same class name: {', '.join(duplicates)}"
        )
