from collections.abc import Mapping, Sequence
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
_LINE_LENGTH = 88


def validate_package_names(
    schemas: Mapping[str, Any], operations: Sequence[Operation], client_name: str
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
    """Render the __init__ of a self-contained single-client package."""
    models = sorted(exported_model_names(schemas))
    _check_no_name_collisions(models, client_name)
    imports = [
        f"from .client import {client_name}",
        "from .exceptions import ApiError",
        *_model_import(".models", models),
    ]
    return _render_init(imports, ["ApiError", client_name, *models])


def render_client_package_init(client_name: str, models: Sequence[str]) -> str:
    """Render the __init__ of one tag package inside a workspace."""
    _check_no_name_collisions(list(models), client_name)
    imports = [
        f"from .client import {client_name}",
        *_model_import(".models", models),
    ]
    return _render_init(imports, [client_name, *models])


def render_workspace_init(
    clients: Sequence[tuple[str, str]],
    models_by_module: Mapping[str, Sequence[str]],
    shared_models: Sequence[str],
) -> str:
    """Render the root __init__ that re-exports every tag client and model."""
    imports = [
        *(
            line
            for module, name in sorted(clients)
            for line in (
                f"from .{module} import {name}",
                *_model_import(f".{module}.models", models_by_module.get(module, ())),
            )
        ),
        "from .shared import ApiError",
        *_model_import(".shared.models", shared_models),
    ]
    names = [
        "ApiError",
        *(name for _, name in clients),
        *shared_models,
        *(name for models in models_by_module.values() for name in models),
    ]
    return _render_init(imports, names)


def _render_init(imports: Sequence[str], exports: Sequence[str]) -> str:
    return render_template(
        TemplateName.PACKAGE_INIT,
        imports="\n".join(imports),
        exports="\n".join(
            f"    {string_literal(name)}," for name in sorted(set(exports))
        ),
    )


def _model_import(module: str, models: Sequence[str]) -> list[str]:
    if not models:
        return []
    single_line = f"from {module} import {', '.join(models)}"
    if len(single_line) <= _LINE_LENGTH:
        return [single_line]
    return [f"from {module} import (", *(f"    {name}," for name in models), ")"]


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
