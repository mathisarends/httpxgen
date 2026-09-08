from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


class TemplateName(StrEnum):
    BINARY_OPERATION = "binary_operation"
    CLIENT = "client"
    ENUM = "enum"
    EXCEPTIONS = "exceptions"
    GENERATED_HEADER = "generated_header"
    HTTP_METHODS = "http_methods"
    MODEL = "model"
    MODELS = "models"
    OPERATION = "operation"
    PACKAGE_INIT = "package_init"
    SERIALIZATION = "serialization"
    SHARED_INIT = "shared_init"
    TRANSPORT = "transport"


def render_template(template_name: TemplateName, **context: object) -> str:
    return _environment().get_template(f"{template_name.value}.jinja2").render(
        **context
    )


@lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(Path(__file__).with_name("templates")),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )


GENERATED_HEADER = render_template(TemplateName.GENERATED_HEADER)
