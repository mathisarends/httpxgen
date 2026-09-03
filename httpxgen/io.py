import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from httpxgen.generator import GenerationError, generate_client
from httpxgen.generator.templates import GENERATED_HEADER
from httpxgen.openapi import APIOperation, HttpMethod, OpenAPISpec, PathItem

_PRESERVE_IF_UNMANAGED = {"__init__.py", "py.typed"}


def load_openapi(path: Path) -> OpenAPISpec:
    """Load an OpenAPI document from a local JSON file."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise GenerationError("OpenAPI document must be a JSON object")
    return _parse_openapi_document(document)


def filter_operations_by_tags(
    spec: OpenAPISpec,
    tags: Sequence[str],
    *,
    schema_tags: Sequence[str] = (),
) -> OpenAPISpec:
    """Return a document containing only operations with one of ``tags``.

    Tags are matched with OR semantics: ``--tag queue --tag callbacks`` includes
    operations tagged ``queue`` or ``callbacks``. Failing early for misspelled
    tags avoids silently producing an empty or incomplete client.
    """
    requested_tags = tuple(dict.fromkeys(tags))
    if not requested_tags:
        return spec.model_copy(deep=True)

    available_tags = _operation_tags(spec)
    requested_schema_tags = tuple(dict.fromkeys(schema_tags))
    unknown_tags = sorted({*requested_tags, *requested_schema_tags} - available_tags)
    if unknown_tags:
        requested = ", ".join(repr(tag) for tag in unknown_tags)
        available = ", ".join(sorted(available_tags)) or "(none)"
        raise GenerationError(
            f"requested OpenAPI tag(s) do not exist: {requested}. "
            f"Available operation tags: {available}"
        )

    selected_paths = _paths_with_tags(spec, requested_tags)
    schema_paths = _paths_with_tags(
        spec,
        (*requested_tags, *requested_schema_tags),
    )
    referenced_schemas = _referenced_schemas(spec, schema_paths)
    selected_paths, referenced_schemas = _canonicalize_schema_names(
        selected_paths,
        referenced_schemas,
    )
    components = spec.components.model_copy(
        deep=True,
        update={"schemas": referenced_schemas},
    )
    return spec.model_copy(
        deep=True,
        update={"components": components, "paths": selected_paths},
    )


def _paths_with_tags(
    spec: OpenAPISpec,
    tags: Sequence[str],
) -> dict[str, PathItem]:
    selected_paths: dict[str, PathItem] = {}
    for path, path_item in spec.paths.items():
        selected_operations: dict[str, APIOperation | None] = {}
        for method in HttpMethod:
            operation = path_item.operation(method)
            if operation is not None and set(operation.tags).intersection(tags):
                selected_operations[method.value] = operation
            else:
                selected_operations[method.value] = None
        if any(selected_operations.values()):
            selected_paths[path] = path_item.model_copy(
                deep=True, update=selected_operations
            )
    return selected_paths


def _referenced_schemas(
    spec: OpenAPISpec,
    paths: dict[str, PathItem],
) -> dict[str, dict[str, Any]]:
    referenced = _schema_references(
        {
            path: path_item.model_dump(by_alias=True, exclude_none=True)
            for path, path_item in paths.items()
        }
    )
    pending = list(referenced)
    while pending:
        name = pending.pop()
        schema = spec.components.schemas.get(name)
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
        return set().union(*(_schema_references(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(_schema_references(item) for item in value))
    if isinstance(value, str) and value.startswith("#/components/schemas/"):
        name = value.removeprefix("#/components/schemas/")
        return {name.replace("~1", "/").replace("~0", "~")}
    return set()


def _canonicalize_schema_names(
    paths: dict[str, PathItem],
    schemas: dict[str, dict[str, Any]],
) -> tuple[dict[str, PathItem], dict[str, dict[str, Any]]]:
    title_counts: dict[str, int] = {}
    for schema in schemas.values():
        title = schema.get("title")
        if isinstance(title, str):
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
            _rewrite_schema_references(
                path_item.model_dump(by_alias=True, exclude_none=True),
                names,
            )
        )
        for path, path_item in paths.items()
    }
    rewritten_schemas = {
        names.get(name, name): _rewrite_schema_references(schema, names)
        for name, schema in schemas.items()
    }
    return rewritten_paths, rewritten_schemas


def _rewrite_schema_references(value: Any, names: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _rewrite_schema_references(item, names) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rewrite_schema_references(item, names) for item in value]
    if isinstance(value, tuple):
        return tuple(_rewrite_schema_references(item, names) for item in value)
    if isinstance(value, str) and value.startswith("#/components/schemas/"):
        prefix = "#/components/schemas/"
        name = value.removeprefix(prefix)
        return f"{prefix}{names.get(name, name)}"
    return value


def write_client(
    *,
    spec: OpenAPISpec,
    package_dir: Path,
    package_name: str | None = None,
    check: bool = False,
) -> list[Path]:
    """Generate into an exact package directory and return changed paths."""
    package_name = package_name or package_dir.name
    rendered = generate_client(spec, package_name)
    managed_output = _managed_output(package_dir, rendered)
    changed = _changed_files(package_dir, managed_output)

    if check:
        if changed:
            paths = ", ".join(str(path) for path in changed)
            raise GenerationError(f"generated client is stale: {paths}")
        return []

    package_dir.mkdir(parents=True, exist_ok=True)
    for relative, content in managed_output.items():
        (package_dir / relative).write_text(content)
    return changed


def _parse_openapi_document(document: dict[str, Any]) -> OpenAPISpec:
    try:
        return OpenAPISpec.model_validate(document)
    except ValidationError as error:
        raise GenerationError(f"invalid OpenAPI document: {error}") from error


def _operation_tags(spec: OpenAPISpec) -> set[str]:
    tags: set[str] = set()
    for path_item in spec.paths.values():
        for method in HttpMethod:
            operation = path_item.operation(method)
            if operation is not None:
                tags.update(operation.tags)
    return tags


def _changed_files(package_dir: Path, rendered: Mapping[str, str]) -> list[Path]:
    return [
        package_dir / relative
        for relative, content in rendered.items()
        if not (package_dir / relative).exists()
        or (package_dir / relative).read_text() != content
    ]


def _managed_output(package_dir: Path, rendered: Mapping[str, str]) -> dict[str, str]:
    managed: dict[str, str] = {}
    for relative, content in rendered.items():
        path = package_dir / relative
        if not path.exists() or _is_generated(path) or path.read_text() == content:
            managed[relative] = content
            continue
        if relative in _PRESERVE_IF_UNMANAGED:
            continue
        raise GenerationError(f"refusing to overwrite non-generated file: {path}")
    return managed


def _is_generated(path: Path) -> bool:
    source = path.read_text()
    return source.startswith(GENERATED_HEADER)
