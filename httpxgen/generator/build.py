from collections import Counter
from collections.abc import Sequence

from httpxgen.generator.client import Layout, render_client, render_serialization
from httpxgen.generator.models import exported_model_names, render_models
from httpxgen.generator.naming import class_name, identifier
from httpxgen.generator.normalize import normalize_inline_schemas
from httpxgen.generator.operations import read_operations, read_security_schemes
from httpxgen.generator.package import (
    render_client_package_init,
    render_package_init,
    render_workspace_init,
    validate_package_names,
)
from httpxgen.generator.templates import (
    GENERATED_HEADER,
    TemplateName,
    render_template,
)
from httpxgen.openapi import OpenAPISpec
from httpxgen.selection import filter_operations_by_tags

_SHARED = "shared"


def generate_client(spec: OpenAPISpec, package_name: str) -> dict[str, str]:
    """Render a single client package as {relative path: file content}."""
    spec = normalize_inline_schemas(spec)
    schemas = spec.components.schemas
    operations = read_operations(spec)
    client_name = f"{class_name(package_name)}Client"
    validate_package_names(schemas, operations, client_name)
    layout = Layout(
        exceptions=f"{package_name}.exceptions",
        serialization=f"{package_name}.serialization",
        models=f"{package_name}.models",
    )
    return _finish(
        {
            "client.py": render_client(operations, schemas, client_name, layout),
            "models.py": render_models(schemas, operations),
            "exceptions.py": render_template(TemplateName.EXCEPTIONS),
            "serialization.py": render_serialization(read_security_schemes(spec)),
            "__init__.py": render_package_init(schemas, client_name),
        }
    )


def generate_workspace(
    spec: OpenAPISpec,
    tags: Sequence[str],
    package_name: str,
    *,
    schema_tags: Sequence[str] = (),
) -> dict[str, str]:
    """Render one client package per tag around a shared support package."""
    tags = tuple(dict.fromkeys(tags))
    spec = normalize_inline_schemas(
        filter_operations_by_tags(spec, tags, schema_tags=schema_tags)
    )
    schemas = spec.components.schemas
    owners = _schema_owners(spec, tags)
    shared_schemas = {
        name: schema for name, schema in schemas.items() if owners[name] is None
    }
    shared_names = frozenset(exported_model_names(shared_schemas))
    shared_module = f"{package_name}.{_SHARED}"

    files = {
        f"{_SHARED}/exceptions.py": render_template(TemplateName.EXCEPTIONS),
        f"{_SHARED}/serialization.py": render_serialization(
            read_security_schemes(spec)
        ),
        f"{_SHARED}/models.py": render_models(schemas, defined=shared_schemas),
        f"{_SHARED}/__init__.py": render_template(TemplateName.SHARED_INIT),
    }
    clients: list[tuple[str, str]] = []
    exports: dict[str, list[str]] = {}
    for tag in tags:
        module = identifier(tag)
        client_name = f"{class_name(module)}Client"
        operations = read_operations(_only(spec, tag, tags, schema_tags))
        validate_package_names(schemas, operations, client_name)
        defined = {name for name, owner in owners.items() if owner == tag}
        layout = Layout(
            exceptions=shared_module,
            serialization=shared_module,
            models=f"{package_name}.{module}.models",
            shared_models=f"{shared_module}.models",
            shared_names=shared_names,
        )
        models = sorted(exported_model_names({name: schemas[name] for name in defined}))
        files[f"{module}/client.py"] = render_client(
            operations, schemas, client_name, layout
        )
        files[f"{module}/models.py"] = render_models(
            schemas,
            operations,
            defined=defined,
            external=[(f"{shared_module}.models", sorted(shared_names))],
        )
        files[f"{module}/__init__.py"] = render_client_package_init(client_name, models)
        clients.append((module, client_name))
        exports[module] = models
    files["__init__.py"] = render_workspace_init(clients, exports, sorted(shared_names))
    return _finish(files)


def _schema_owners(spec: OpenAPISpec, tags: Sequence[str]) -> dict[str, str | None]:
    """Map every schema to the single tag using it, or None when it is shared."""
    reachable = {
        tag: set(filter_operations_by_tags(spec, [tag]).components.schemas)
        for tag in tags
    }
    counts = Counter(name for names in reachable.values() for name in names)
    return {
        name: next(
            (tag for tag in tags if counts[name] == 1 and name in reachable[tag]),
            None,
        )
        for name in spec.components.schemas
    }


def _only(
    spec: OpenAPISpec, tag: str, tags: Sequence[str], schema_tags: Sequence[str]
) -> OpenAPISpec:
    others = [item for item in tags if item != tag]
    return filter_operations_by_tags(spec, [tag], schema_tags=[*others, *schema_tags])


def _finish(files: dict[str, str]) -> dict[str, str]:
    return {
        relative: f"{GENERATED_HEADER}\n\n{content.rstrip()}\n"
        for relative, content in files.items()
    } | {"py.typed": ""}
