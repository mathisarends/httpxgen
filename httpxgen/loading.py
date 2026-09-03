import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from httpxgen.generator import GenerationError
from httpxgen.openapi import OpenAPISpec


def load_openapi(path: Path) -> OpenAPISpec:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise GenerationError("OpenAPI document must be a JSON object")
    return _parse_document(document)


def _parse_document(document: dict[str, Any]) -> OpenAPISpec:
    try:
        return OpenAPISpec.model_validate(document)
    except ValidationError as error:
        raise GenerationError(f"invalid OpenAPI document: {error}") from error
