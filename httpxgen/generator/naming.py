import json
import keyword
import re
from collections.abc import Sequence


def class_name(value: str) -> str:
    words = re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+", value)
    result = "".join(word[:1].upper() + word[1:] for word in words) or "Model"
    return f"Model{result}" if result[0].isdigit() else result


def identifier(value: str) -> str:
    value = re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()
    value = re.sub(r"\W", "_", value)
    if not value or value[0].isdigit():
        value = f"value_{value}"
    if keyword.iskeyword(value):
        value += "_"
    return value


def field_identifier(value: str) -> str:
    result = identifier(value)
    if result.startswith("model_"):
        result += "_"
    return result


def argument_identifier(value: str) -> str:
    result = identifier(value)
    if result in _OPERATION_LOCALS:
        result += "_arg"
    return result


def query_identifier(value: str) -> str:
    result = argument_identifier(value)
    if result.startswith("_"):
        return f"field{result}"
    if result.startswith("model_"):
        return f"field_{result}"
    return result


_OPERATION_LOCALS = {
    "path",
    "params",
    "query",
    "headers",
    "cookies",
    "files",
    "form_data",
    "body_data",
    "body_arguments",
    "json_body",
    "response",
    "detail",
    "error",
    "validation_error",
    "response_content_type",
    "response_stack",
    "response_context",
    "binary_stream",
    "stream_result",
    "binary_content",
    "serialize_json_part",
    "serialize_form_body",
    "stream",
    "item",
    "scalar",
    "apply_security",
    "serialize_path",
    "serialize_query",
    "serialize_simple",
    "serialize_json_body",
    "upload_file_part",
}


def enum_member(value: str) -> str:
    result = re.sub(r"\W+", "_", value).strip("_").upper() or "EMPTY"
    return f"VALUE_{result}" if result[0].isdigit() else result


def string_literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def used_names(source: str, candidates: Sequence[str]) -> list[str]:
    return [name for name in candidates if re.search(rf"\b{re.escape(name)}\b", source)]
