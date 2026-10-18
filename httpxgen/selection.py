from collections.abc import Sequence
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.operations import resolve_path_item
from httpxgen.openapi import (
    APIOperation,
    Components,
    HttpMethod,
    OpenAPISpec,
    PathItem,
    get_operation,
    unsupported_operations,
)
from httpxgen.references import COMPONENT_KINDS, reference_values, rewrite_references


def filter_operations_by_tags(
    spec: OpenAPISpec,
    tags: Sequence[str],
    *,
    schema_tags: Sequence[str] = (),
) -> OpenAPISpec:
    requested = tuple(dict.fromkeys(tags))
    if not requested:
        return spec.model_copy(deep=True)

    spec = spec.model_copy(
        update={
            "paths": {
                path: resolve_path_item(item, spec) for path, item in spec.paths.items()
            }
        }
    )

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

    selected_paths = paths_with_tags(spec, requested)
    schema_paths = paths_with_tags(spec, (*requested, *schema_only))
    retained = _referenced_components(spec, schema_paths)
    selected_paths, retained = _canonicalize_schema_names(selected_paths, retained)
    components = Components.model_validate(retained)
    return spec.model_copy(
        deep=True,
        update={"components": components, "paths": selected_paths},
    )


def _operation_tags(spec: OpenAPISpec) -> set[str]:
    return {
        tag
        for path_item in spec.paths.values()
        for operation in (
            *(get_operation(path_item, method) for method in HttpMethod),
            *unsupported_operations(path_item).values(),
        )
        if operation is not None
        for tag in operation.tags
    }


def paths_with_tags(
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
        # Keep OpenAPI 3.2 QUERY/additional operations only when selected, so
        # generation reports them instead of silently dropping them.
        query = path_item.query
        operations["query"] = (
            query if query is not None and set(query.tags).intersection(tags) else None
        )
        additional = {
            method: operation
            for method, operation in path_item.additional_operations.items()
            if set(operation.tags).intersection(tags)
        }
        if any(operations.values()) or additional:
            selected[path] = path_item.model_copy(
                deep=True,
                update={**operations, "additional_operations": additional},
            )
    return selected


def _referenced_components(
    spec: OpenAPISpec,
    paths: dict[str, PathItem],
) -> dict[str, Any]:
    components = spec.components.model_dump(by_alias=True, exclude_none=True)
    referenced = _component_references(
        {
            "paths": {
                path: item.model_dump(by_alias=True, exclude_none=True)
                for path, item in paths.items()
            }
        }
    )
    pending = list(referenced)
    while pending:
        section, name = pending.pop()
        component = components.get(section, {}).get(name)
        if component is None:
            continue
        for dependency in (
            _component_references(component, COMPONENT_KINDS.get(section, "schema"))
            - referenced
        ):
            referenced.add(dependency)
            pending.append(dependency)
    return {
        section: {
            name: value
            for name, value in values.items()
            if section == "securitySchemes" or (section, name) in referenced
        }
        for section, values in components.items()
        if isinstance(values, dict)
    }


def _component_references(value: Any, kind: str = "document") -> set[tuple[str, str]]:
    result = set()
    for reference in reference_values(value, kind, mappings=True):
        parts = reference.split("/", 3)
        if reference.startswith("#/components/") and len(parts) == 4:
            result.add((parts[2], parts[3].replace("~1", "/").replace("~0", "~")))
    return result


def _canonicalize_schema_names(
    paths: dict[str, PathItem],
    components: dict[str, Any],
) -> tuple[dict[str, PathItem], dict[str, Any]]:
    schemas = components.get("schemas", {})
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
        return paths, components

    rewritten_paths = {
        path: PathItem.model_validate(
            _rewrite_references(
                item.model_dump(by_alias=True, exclude_none=True), names, "path_item"
            )
        )
        for path, item in paths.items()
    }
    rewritten_schemas = {
        names.get(name, name): _rewrite_references(schema, names, "schema")
        for name, schema in schemas.items()
    }
    rewritten_components = _rewrite_references(components, names, "components")
    rewritten_components["schemas"] = rewritten_schemas
    return rewritten_paths, rewritten_components


def _rewrite_references(
    value: Any, names: dict[str, str], kind: str = "document"
) -> Any:
    def transform(reference: str) -> str:
        prefix = "#/components/schemas/"
        if reference.startswith(prefix):
            name = reference.removeprefix(prefix).replace("~1", "/").replace("~0", "~")
            canonical = names.get(name, name).replace("~", "~0").replace("/", "~1")
            return f"{prefix}{canonical}"
        return names.get(reference, reference)

    return rewrite_references(value, transform, kind)
