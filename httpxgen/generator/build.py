from collections import Counter
from collections.abc import Sequence
from typing import Literal

from httpxgen.generator.client import Layout, render_client, render_serialization
from httpxgen.generator.errors import GenerationError
from httpxgen.generator.models import (
    discriminator_dependencies,
    exported_model_names,
    render_models,
)
from httpxgen.generator.naming import class_name, identifier
from httpxgen.generator.normalize import normalize_inline_schemas
from httpxgen.generator.operations import (
    read_operations,
    read_security_schemes,
    response_model_names,
)
from httpxgen.generator.package import (
    render_client_package_init,
    render_package_init,
    render_workspace_init,
    validate_package_names,
    validate_workspace_names,
)
from httpxgen.generator.schema import schema_dependencies
from httpxgen.generator.templates import (
    GENERATED_HEADER,
    TemplateName,
    render_template,
)
from httpxgen.openapi import OpenAPISpec
from httpxgen.selection import filter_operations_by_tags, paths_with_tags

_SHARED = "shared"
type HttpClientBackend = Literal["protocol", "httpx", "httpx2"]
HTTP_CLIENT_BACKENDS = ("protocol", "httpx", "httpx2")


def generate_client(
    spec: OpenAPISpec,
    package_name: str,
    *,
    client_name: str | None = None,
    http_client: HttpClientBackend = "protocol",
) -> dict[str, str]:
    """Render a single client package as {relative path: file content}."""
    _validate_http_client(http_client)
    spec = normalize_inline_schemas(spec)
    schemas = spec.components.schemas
    operations = read_operations(spec)
    client_name = client_name or f"{class_name(package_name.rsplit('.', 1)[-1])}Client"
    validate_package_names(schemas, operations, client_name)
    layout = Layout(
        exceptions=f"{package_name}.exceptions",
        serialization=f"{package_name}.serialization",
        models=f"{package_name}.models",
        http_methods=f"{package_name}.http_methods",
        transport=f"{package_name}.transport",
    )
    return _finish(
        {
            "client.py": render_client(operations, schemas, client_name, layout),
            "models.py": render_models(
                schemas, operations, transport_module=layout.transport
            ),
            "exceptions.py": render_template(
                TemplateName.EXCEPTIONS, transport_module=layout.transport
            ),
            "http_methods.py": render_template(TemplateName.HTTP_METHODS),
            "transport.py": render_template(
                TemplateName.TRANSPORT,
                http_client=http_client,
                exceptions_module=layout.exceptions,
            ),
            "serialization.py": render_serialization(read_security_schemes(spec)),
            "__init__.py": render_package_init(schemas, client_name, operations),
        }
    )


def generate_workspace(
    spec: OpenAPISpec,
    tags: Sequence[str],
    package_name: str,
    *,
    schema_tags: Sequence[str] = (),
    http_client: HttpClientBackend = "protocol",
) -> dict[str, str]:
    """Render one client package per tag around a shared support package."""
    _validate_http_client(http_client)
    tags = tuple(dict.fromkeys(tags))
    spec = normalize_inline_schemas(
        filter_operations_by_tags(spec, tags, schema_tags=schema_tags)
    )
    schemas = spec.components.schemas
    operations_by_tag = {
        tag: read_operations(
            spec.model_copy(update={"paths": paths_with_tags(spec, [tag])})
        )
        for tag in tags
    }
    validate_workspace_names(
        schemas,
        operations_by_tag,
        [f"{class_name(identifier(tag))}Client" for tag in tags],
    )
    owners = _schema_owners(spec, tags)
    shared_schemas = {
        name: schema for name, schema in schemas.items() if owners[name] is None
    }
    shared_names = frozenset(exported_model_names(shared_schemas))
    shared_module = f"{package_name}.{_SHARED}"

    files = {
        f"{_SHARED}/exceptions.py": render_template(
            TemplateName.EXCEPTIONS, transport_module=f"{shared_module}.transport"
        ),
        f"{_SHARED}/http_methods.py": render_template(TemplateName.HTTP_METHODS),
        f"{_SHARED}/transport.py": render_template(
            TemplateName.TRANSPORT,
            http_client=http_client,
            exceptions_module=f"{package_name}.{_SHARED}.exceptions",
        ),
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
        operations = operations_by_tag[tag]
        validate_package_names(schemas, operations, client_name)
        defined = {name for name, owner in owners.items() if owner == tag}
        layout = Layout(
            exceptions=shared_module,
            serialization=shared_module,
            models=f"{package_name}.{module}.models",
            http_methods=shared_module,
            transport=shared_module,
            shared_models=f"{shared_module}.models",
            shared_names=shared_names,
        )
        models = sorted(
            [
                *exported_model_names({name: schemas[name] for name in defined}),
                *(
                    name
                    for operation in operations
                    for name in response_model_names(operation)
                ),
            ]
        )
        files[f"{module}/client.py"] = render_client(
            operations, schemas, client_name, layout
        )
        files[f"{module}/models.py"] = render_models(
            schemas,
            operations,
            defined=defined,
            external=[(f"{shared_module}.models", sorted(shared_names))],
            transport_module=layout.transport,
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
    owners = {
        name: next(
            (tag for tag in tags if counts[name] == 1 and name in reachable[tag]),
            None,
        )
        for name in spec.components.schemas
    }
    generated = discriminator_dependencies(spec.components.schemas)
    changed = True
    while changed:
        changed = False
        for name, schema in spec.components.schemas.items():
            dependencies = schema_dependencies(schema) | generated.get(name, set())
            for dependency in dependencies:
                if (
                    dependency in owners
                    and owners[dependency] is not None
                    and owners[dependency] != owners[name]
                ):
                    owners[dependency] = None
                    changed = True
    return owners


def _finish(files: dict[str, str]) -> dict[str, str]:
    return {
        relative: f"{GENERATED_HEADER}\n\n{content.rstrip()}\n"
        for relative, content in files.items()
    } | {"py.typed": ""}


def _validate_http_client(http_client: str) -> None:
    if http_client not in HTTP_CLIENT_BACKENDS:
        choices = ", ".join(HTTP_CLIENT_BACKENDS)
        raise GenerationError(
            f"unsupported HTTP client {http_client!r}; choose one of: {choices}"
        )
