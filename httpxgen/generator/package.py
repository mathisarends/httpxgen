from collections.abc import Mapping, Sequence
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.models import exported_model_names, exported_model_sources
from httpxgen.generator.naming import string_literal
from httpxgen.generator.operations import (
    Operation,
    query_model_name,
    query_parameters,
    response_model_names,
)
from httpxgen.generator.templates import TemplateName, render_template

_RESERVED_NAMES = {
    "Annotated",
    "Any",
    "ApiError",
    "ApiResponse",
    "BaseModel",
    "ConfigDict",
    "Field",
    "HttpMethods",
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
    response_models = [
        name for operation in operations for name in response_model_names(operation)
    ]
    generated_models = [*exported_models, *query_models, *response_models]
    _check_no_name_collisions(generated_models, client_name)
    method_conflicts = sorted(
        _CLIENT_METHODS.intersection(operation.name for operation in operations)
    )
    if method_conflicts:
        raise GenerationError(
            "operationId values conflict with generated client methods: "
            + ", ".join(method_conflicts)
        )


def validate_workspace_names(
    schemas: Mapping[str, Any],
    operations_by_tag: Mapping[str, Sequence[Operation]],
    client_names: Sequence[str],
) -> None:
    """Check every generated name across all tags before a module is rendered.

    Per-tag validation cannot see that two tags bind the same name to different
    definitions; the workspace `__init__` would silently re-export only one.
    """
    sources: dict[str, set[str]] = {}
    for name, source in exported_model_sources(schemas):
        sources.setdefault(name, set()).add(source)
    for operations in operations_by_tag.values():
        for operation in operations:
            # Identify by route, not operationId: one operation carrying several
            # tags is generated per tag and must not look like a collision.
            route = f"{operation.method.upper()} {operation.path}"
            for name in response_model_names(operation):
                sources.setdefault(name, set()).add(f"response model of {route}")
            if query_parameters(operation):
                sources.setdefault(query_model_name(operation), set()).add(
                    f"query model of {route}"
                )
    for client_name in client_names:
        sources.setdefault(client_name, set()).add(f"client class {client_name}")

    conflicts = [
        f"{name} ({', '.join(sorted(origins))})"
        for name, origins in sorted(sources.items())
        if len(origins) > 1
    ]
    if conflicts:
        raise GenerationError(
            "generated names collide across the workspace: "
            + "; ".join(conflicts)
            + "; rename the schema(s) or operationId(s) in the OpenAPI document"
        )
    reserved = sorted(_RESERVED_NAMES.intersection(sources))
    if reserved:
        raise GenerationError(
            f"generated name(s) {', '.join(reserved)} conflict with a generated "
            "symbol; rename the schema(s) in the OpenAPI document"
        )


def render_package_init(
    schemas: Mapping[str, Any], client_name: str, operations: Sequence[Operation] = ()
) -> str:
    """Render the __init__ of a self-contained single-client package."""
    models = sorted(
        [
            *exported_model_names(schemas),
            *(
                name
                for operation in operations
                for name in response_model_names(operation)
            ),
        ]
    )
    _check_no_name_collisions(models, client_name)
    imports = [
        f"from .client import {client_name}",
        "from .exceptions import ApiError",
        "from .http_methods import HttpMethods",
        *_model_import(".models", models),
    ]
    return _render_init(imports, ["ApiError", "HttpMethods", client_name, *models])


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
        "from .shared import ApiError, HttpMethods",
        *_model_import(".shared.models", shared_models),
    ]
    names = [
        "ApiError",
        "HttpMethods",
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
