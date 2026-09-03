"""Renders a typed async httpx client package from an OpenAPI spec."""

from httpxgen.generator.client import generate_client_module, read_operations
from httpxgen.generator.errors import GenerationError
from httpxgen.generator.models import class_name, generate_models
from httpxgen.generator.package import generate_package_init
from httpxgen.generator.templates import GENERATED_HEADER, TemplateName, render_template
from httpxgen.openapi import OpenAPISpec

__all__ = ["GenerationError", "generate_client"]


def generate_client(spec: OpenAPISpec, package_name: str) -> dict[str, str]:
    """Render a complete client package as {relative path: file content}."""
    schemas = spec.components.schemas
    client_name = f"{class_name(package_name)}Client"
    operations = read_operations(spec)

    managed_files = {
        "client.py": generate_client_module(operations, schemas, client_name),
        "models.py": generate_models(schemas),
        "exceptions.py": render_template(TemplateName.EXCEPTIONS),
        "__init__.py": generate_package_init(schemas, client_name),
    }
    return {
        relative: f"{GENERATED_HEADER}\n\n{content.rstrip()}\n"
        for relative, content in managed_files.items()
    } | {"py.typed": ""}
