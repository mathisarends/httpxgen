from httpxgen.generator.client import render_client
from httpxgen.generator.models import render_models
from httpxgen.generator.normalize import normalize_inline_schemas
from httpxgen.generator.naming import class_name
from httpxgen.generator.operations import read_operations
from httpxgen.generator.package import render_package_init
from httpxgen.generator.templates import (
    GENERATED_HEADER,
    TemplateName,
    render_template,
)
from httpxgen.openapi import OpenAPISpec


def generate_client(spec: OpenAPISpec, package_name: str) -> dict[str, str]:
    """Render a complete client package as {relative path: file content}."""
    spec = normalize_inline_schemas(spec)
    schemas = spec.components.schemas
    client_name = f"{class_name(package_name)}Client"
    operations = read_operations(spec)

    managed_files = {
        "client.py": render_client(operations, schemas, client_name),
        "models.py": render_models(schemas, operations),
        "exceptions.py": render_template(TemplateName.EXCEPTIONS),
        "__init__.py": render_package_init(schemas, client_name),
    }
    return {
        relative: f"{GENERATED_HEADER}\n\n{content.rstrip()}\n"
        for relative, content in managed_files.items()
    } | {"py.typed": ""}
