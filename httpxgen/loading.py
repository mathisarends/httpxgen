import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError
import yaml

from httpxgen.generator import GenerationError
from httpxgen.openapi import OpenAPISpec


def load_openapi(path: Path) -> OpenAPISpec:
    source = path.read_text(encoding="utf-8-sig")
    try:
        document = json.loads(source) if path.suffix.lower() == ".json" else yaml.safe_load(source)
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise GenerationError(f"cannot parse OpenAPI document: {error}") from error
    if not isinstance(document, dict):
        raise GenerationError("OpenAPI document must be an object")
    return _parse_document(document)


def _parse_document(document: dict[str, Any]) -> OpenAPISpec:
    try:
        return OpenAPISpec.model_validate(document)
    except ValidationError as error:
        raise GenerationError(f"invalid OpenAPI document: {error}") from error
