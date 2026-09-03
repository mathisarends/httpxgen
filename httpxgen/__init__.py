"""httpxgen: generate a typed async httpx client from an OpenAPI 3.x spec."""

from httpxgen.generator import GenerationError, generate_client
from httpxgen.io import filter_operations_by_tags, load_openapi, write_client
from httpxgen.openapi import OpenAPISpec

__all__ = [
    "GenerationError",
    "OpenAPISpec",
    "filter_operations_by_tags",
    "generate_client",
    "load_openapi",
    "write_client",
]
