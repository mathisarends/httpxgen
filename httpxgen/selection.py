from collections.abc import Sequence
from typing import Any

from httpxgen.generator import GenerationError
from httpxgen.openapi import (
    APIOperation,
    HttpMethod,
    OpenAPISpec,
    PathItem,
    get_operation,
)


def filter_operations_by_tags(
    spec: OpenAPISpec,
    tags: Sequence[str],
    *,
    schema_tags: Sequence[str] = (),
) -> OpenAPISpec:
    requested = tuple(dict.fromkeys(tags))
    if not requested:
        return spec.model_copy(deep=True)

    available = _operation_tags(spec)
    schema_only = tuple(dict.fromkeys(schema_tags))
    unknown = sorted({*requested, *schema_only} - available)
    if unknown:
        unknown_text = ", ".join(repr(tag) for tag in unknown)
        available_text = ", ".join(sorted(available)) or "(none)"
        raise GenerationError(
            f"requested OpenAPI tag(s) do not exist: {unknown_text}. "
            f"Available operation tags: {available_text}"
        )

    selected_paths = _paths_with_tags(spec, requested)
    schema_paths = _paths_with_tags(spec, (*requested, *schema_only))
    schemas = _referenced_schemas(spec, schema_paths)
    selected_paths, schemas = _canonicalize_schema_names(selected_paths, schemas)
    components = spec.components.model_copy(deep=True, update={"schemas": schemas})
    return spec.model_copy(
        deep=True,
        update={"components": components, "paths": selected_paths},
    )


def _operation_tags(spec: OpenAPISpec) -> set[str]:
    return {
        tag
        for path_item in spec.paths.values()
        for method in HttpMethod
        if (operation := get_operation(path_item, method)) is not None
        for tag in operation.tags
    }


def _paths_with_tags(
    spec: OpenAPISpec,
    tags: Sequence[str],
) -> dict[str, PathItem]:
    selected: dict[str, PathItem] = {}
    for path, path_item in spec.paths.items():
        operations: dict[str, APIOperation | None] = {
            method.value: operation
            if (operation := get_operation(path_item, method)) is not None
            and set(operation.tags).intersection(tags)
            else None
            for method in HttpMethod
        }
        if any(operations.values()):
            selected[path] = path_item.model_copy(deep=True, update=operations)
    return selected


def _referenced_schemas(
    spec: OpenAPISpec,
    paths: dict[str, PathItem],
) -> dict[str, dict[str, Any]]:
    referenced = _schema_references(
        {
            path: item.model_dump(by_alias=True, exclude_none=True)
            for path, item in paths.items()
        }
    )
    pending = list(referenced)
    while pending:
        schema = spec.components.schemas.get(pending.pop())
        if schema is None:
            continue
        for dependency in _schema_references(schema) - referenced:
            referenced.add(dependency)
            pending.append(dependency)
    return {
        name: schema
        for name, schema in spec.components.schemas.items()
        if name in referenced
    }


def _schema_references(value: Any) -> set[str]:
    if isinstance(value, dict):
        references: set[str] = set()
        for item in value.values():
            references.update(_schema_references(item))
        return references
    if isinstance(value, (list, tuple)):
        references = set()
        for item in value:
            references.update(_schema_references(item))
        return references
    prefix = "#/components/schemas/"
    if isinstance(value, str) and value.startswith(prefix):
        name = value.removeprefix(prefix)
        return {name.replace("~1", "/").replace("~0", "~")}
    return set()


def _canonicalize_schema_names(
    paths: dict[str, PathItem],
    schemas: dict[str, dict[str, Any]],
) -> tuple[dict[str, PathItem], dict[str, dict[str, Any]]]:
    title_counts: dict[str, int] = {}
    for schema in schemas.values():
        if isinstance((title := schema.get("title")), str):
            title_counts[title] = title_counts.get(title, 0) + 1

    names = {
        name: title
        for name, schema in schemas.items()
        if isinstance((title := schema.get("title")), str)
        and title_counts[title] == 1
        and (title == name or title not in schemas)
    }
    if all(name == canonical for name, canonical in names.items()):
        return paths, schemas

    rewritten_paths = {
        path: PathItem.model_validate(
            _rewrite_references(item.model_dump(by_alias=True, exclude_none=True), names)
        )
        for path, item in paths.items()
    }
    rewritten_schemas = {
        names.get(name, name): _rewrite_references(schema, names)
        for name, schema in schemas.items()
    }
    return rewritten_paths, rewritten_schemas


def _rewrite_references(value: Any, names: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _rewrite_references(item, names) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_references(item, names) for item in value]
    if isinstance(value, tuple):
        return tuple(_rewrite_references(item, names) for item in value)
    prefix = "#/components/schemas/"
    if isinstance(value, str) and value.startswith(prefix):
        name = value.removeprefix(prefix)
        return f"{prefix}{names.get(name, name)}"
    return value
