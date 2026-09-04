import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from httpxgen.generator.naming import class_name, string_literal, used_names
from httpxgen.generator.operations import (
    NO_DEFAULT,
    Body,
    Operation,
    Parameter,
    Response,
    ResponseContent,
    SecurityScheme,
    query_model_name,
    query_parameters,
)
from httpxgen.generator.schema import ordered_schemas
from httpxgen.generator.templates import TemplateName, render_template

_LINE_LENGTH = 88
_INDENT = " " * 8


@dataclass(frozen=True)
class Layout:
    """Where a generated client imports its support modules and models from."""

    exceptions: str
    serialization: str
    models: str
    http_methods: str = ""
    shared_models: str = ""
    shared_names: frozenset[str] = frozenset()


def render_client(
    operations: Sequence[Operation],
    schemas: Mapping[str, Any],
    client_name: str,
    layout: Layout,
) -> str:
    methods = "\n\n".join(_render_operation(operation) for operation in operations)
    annotations = " ".join(
        [
            *(item.annotation for op in operations for item in op.parameters),
            *(op.body_annotation or "" for op in operations),
            *(item.annotation for op in operations for item in op.responses),
            *(
                item.result_annotation or ""
                for op in operations
                for item in op.responses
            ),
            *(
                header.annotation
                for op in operations
                for response in op.responses
                for header in response.headers
            ),
        ]
    )
    model_names = sorted(
        [
            *(
                class_name(name)
                for name in ordered_schemas(schemas)
                if re.search(rf"\b{re.escape(class_name(name))}\b", annotations)
            ),
            *(
                query_model_name(operation)
                for operation in operations
                if query_parameters(operation)
            ),
            *(
                response.result_annotation
                for operation in operations
                for response in operation.responses
                if response.result_annotation is not None
            ),
        ]
    )
    return render_template(
        TemplateName.CLIENT,
        imports=_render_client_imports(operations, annotations, model_names, layout),
        client_name=client_name,
        methods=methods,
    )


def render_serialization(schemes: Sequence[SecurityScheme]) -> str:
    entries = "".join(
        _wrap(
            f"{string_literal(scheme.name)}: SecurityScheme("
            + ", ".join(
                string_literal(value or "")
                for value in (
                    scheme.kind,
                    scheme.location,
                    scheme.parameter_name,
                    scheme.prefix,
                )
            )
            + "),",
            "    ",
        )
        for scheme in sorted(schemes, key=lambda item: item.name)
    )
    return render_template(
        TemplateName.SERIALIZATION,
        security_schemes=f"{{\n{entries}}}" if entries else "{}",
    )


def _render_client_imports(
    operations: Sequence[Operation],
    annotations: str,
    model_names: Sequence[str],
    layout: Layout,
) -> str:
    typing_names = used_names(annotations, ("Literal",))
    has_content_variants = any(
        len(_operation_bodies(operation)) > 1 for operation in operations
    )
    if has_content_variants:
        typing_names.append("Literal")
    if has_content_variants or any(
        _has_optional_body(operation) for operation in operations
    ):
        typing_names.insert(0, "Any")
    typing_names.append("Self")
    lines = ["from collections.abc import Mapping"]
    datetime_names = used_names(annotations, ("date", "datetime"))
    if datetime_names:
        lines.append(f"from datetime import {', '.join(datetime_names)}")
    lines.append(f"from typing import {', '.join(dict.fromkeys(typing_names))}")
    if "UUID" in annotations:
        lines.append("from uuid import UUID")
    lines.extend(["", "import httpx"])
    if _needs_type_adapter(operations):
        lines.append("from pydantic import TypeAdapter")
    lines.append("")
    by_module: dict[str, list[str]] = {}
    by_module.setdefault(layout.exceptions, []).append("ApiError")
    by_module.setdefault(layout.http_methods or layout.serialization, []).append(
        "HttpMethods"
    )
    by_module.setdefault(layout.serialization, []).extend(
        _serialization_helpers(operations)
    )
    for name in model_names:
        module = layout.shared_models if name in layout.shared_names else layout.models
        by_module.setdefault(module, []).append(name)
    lines.extend(
        _render_import(f"from {module} import", sorted(names))
        for module, names in sorted(by_module.items())
        if names
    )
    return "\n".join(lines)


def _render_import(prefix: str, names: Sequence[str]) -> str:
    single_line = f"{prefix} {', '.join(names)}"
    if len(single_line) <= _LINE_LENGTH:
        return single_line
    return "\n".join([f"{prefix} (", *(f"    {name}," for name in names), ")"])


def _serialization_helpers(operations: Sequence[Operation]) -> list[str]:
    helpers: set[str] = set()
    for operation in operations:
        if operation.security:
            helpers.add("apply_security")
        for parameter in operation.parameters:
            helpers.add(_SERIALIZERS[parameter.location])
    return sorted(helpers)


def _needs_type_adapter(operations: Sequence[Operation]) -> bool:
    return (
        any(operation.body for operation in operations)
        or any(
            content.kind == "json" and content.model_annotation is None
            for operation in operations
            for response in operation.responses
            for content in _response_contents(response)
        )
        or any(
            header.annotation != "str"
            for operation in operations
            for response in operation.responses
            for header in response.headers
        )
    )


def _render_operation(operation: Operation) -> str:
    arguments: list[tuple[str, bool]] = []
    for parameter in operation.parameters:
        default = _parameter_default(parameter)
        arguments.append(
            (f"{parameter.name}: {parameter.annotation}{default}", parameter.required)
        )
    if operation.body_annotation:
        annotation = operation.body_annotation
        default = ""
        if not operation.body_required:
            annotation, default = f"{annotation} | None", " = None"
        arguments.append((f"body: {annotation}{default}", operation.body_required))
    arguments.sort(key=lambda item: not item[1])
    signature = "".join(f"        {value},\n" for value, _ in arguments)
    bodies = _operation_bodies(operation)
    content_type_argument = ""
    if len(bodies) > 1:
        choices = ", ".join(string_literal(item.media_type) for item in bodies)
        content_type_argument = (
            f"        content_type: Literal[{choices}] = "
            f"{string_literal(bodies[0].media_type)},\n"
        )
    successes = [
        item.result_annotation or item.annotation
        for item in operation.responses
        if item.success
    ]
    blocks = [
        _render_path(operation),
        _render_query(operation),
        _render_headers(operation),
        _render_cookies(operation),
        _render_security(operation),
        _render_body(operation),
    ]
    return render_template(
        TemplateName.OPERATION,
        operation=operation,
        signature=signature,
        content_type_argument=content_type_argument,
        return_annotation=" | ".join(dict.fromkeys(successes)),
        assignments="\n".join(block for block in blocks if block),
        request_arguments=_render_request_arguments(operation),
        response_handling=_render_response_handling(operation.responses),
    ).rstrip("\n")


def _parameter_default(parameter: Parameter) -> str:
    if parameter.default is not NO_DEFAULT:
        return f" = {parameter.default_source or repr(parameter.default)}"
    return "" if parameter.required else " = None"


def _render_path(operation: Operation) -> str:
    lines = [f"{_INDENT}path = {string_literal(operation.path)}\n"]
    for parameter in _by_location(operation, "path"):
        placeholder = string_literal(f"{{{parameter.wire_name}}}")
        lines.append(
            _wrap(
                f"path = path.replace({placeholder}, "
                f"{_serialize_call(parameter, parameter.name)})",
                _INDENT,
            )
        )
    return "".join(lines)


def _render_query(operation: Operation) -> str:
    if not _needs_query(operation):
        return ""
    parameters = query_parameters(operation)
    lines: list[str] = []
    if parameters:
        lines.append(f"{_INDENT}params = {query_model_name(operation)}(\n")
        lines.extend(f"{_INDENT}    {item.name}={item.name},\n" for item in parameters)
        lines.append(f"{_INDENT})\n")
    lines.append(f"{_INDENT}query: list[tuple[str, str]] = []\n")
    for parameter in parameters:
        call = _serialize_call(parameter, f"params.{parameter.name}")
        lines.append(_guarded(parameter, f"query.extend({call})"))
    return "".join(lines)


def _render_headers(operation: Operation) -> str:
    if not _needs_headers(operation):
        return ""
    parameters = _by_location(operation, "header")
    accepted = _accept_header(operation)
    content_type = _content_type_header(operation)
    lines = [f"{_INDENT}headers = dict(self._headers)\n"]
    if accepted:
        lines.append(
            _wrap(f'headers.setdefault("Accept", {string_literal(accepted)})', _INDENT)
        )
    if content_type:
        lines.append(
            _wrap(
                f'headers.setdefault("Content-Type", {string_literal(content_type)})',
                _INDENT,
            )
        )
    for parameter in parameters:
        lines.append(
            _guarded(
                parameter,
                f"headers[{string_literal(parameter.wire_name)}] = "
                f"{_serialize_call(parameter, parameter.name)}",
            )
        )
    return "".join(lines)


def _render_cookies(operation: Operation) -> str:
    if not _needs_cookies(operation):
        return ""
    parameters = _by_location(operation, "cookie")
    lines = [f"{_INDENT}cookies: dict[str, str] = {{}}\n"]
    for parameter in parameters:
        lines.append(
            _guarded(
                parameter,
                f"cookies[{string_literal(parameter.wire_name)}] = "
                f"{_serialize_call(parameter, parameter.name)}",
            )
        )
    return "".join(lines)


def _render_security(operation: Operation) -> str:
    if not operation.security:
        return ""
    requirements = ", ".join(
        _tuple_literal(requirement) for requirement in operation.security
    )
    headers = "headers" if _needs_headers(operation) else "{}"
    query = "query" if _needs_query(operation) else "[]"
    cookies = "cookies" if _needs_cookies(operation) else "{}"
    return _wrap(
        f"apply_security(self._credentials, [{requirements}], "
        f"{headers}, {query}, {cookies})",
        _INDENT,
    )


def _tuple_literal(names: Sequence[str]) -> str:
    items = ", ".join(string_literal(name) for name in names)
    return f"({items},)" if len(names) == 1 else f"({items})"


def _render_body(operation: Operation) -> str:
    bodies = _operation_bodies(operation)
    if not bodies:
        return ""
    body = bodies[0]
    if len(bodies) > 1:
        lines = [f"{_INDENT}body_arguments: dict[str, Any] = {{}}\n"]
        indent = _INDENT
        if not body.required:
            lines.append(f"{_INDENT}if body is not None:\n")
            indent += "    "
        for index, variant in enumerate(bodies):
            keyword = "if" if index == 0 else "elif"
            lines.append(
                f"{indent}{keyword} content_type == "
                f"{string_literal(variant.media_type)}:\n"
            )
            lines.extend(_render_body_variant(variant, indent + "    "))
        return "".join(lines)
    if body.required:
        return "".join(_render_required_body(body))

    lines = [
        f"{_INDENT}body_arguments: dict[str, Any] = {{}}\n",
        f"{_INDENT}if body is not None:\n",
    ]
    indent = f"{_INDENT}    "
    lines.extend(_render_body_variant(body, indent))
    return "".join(lines)


def _render_body_variant(body: Body, indent: str) -> list[str]:
    if body.kind == "json":
        lines = [
            f'{indent}body_arguments["json"] = TypeAdapter(',
            f"{body.annotation}).dump_python(\n",
            f'{indent}    body, mode="json", by_alias=True, exclude_none=True\n',
            f"{indent})\n",
        ]
    elif body.kind in {"form", "multipart"}:
        lines = [
            f"{indent}body_data = TypeAdapter({body.annotation}).dump_python(\n",
            f'{indent}    body, mode="python", by_alias=True, exclude_none=True\n',
            f"{indent})\n",
        ]
        if body.kind == "form":
            lines.append(f'{indent}body_arguments["data"] = body_data\n')
        else:
            lines.extend(
                [
                    f"{indent}files = {{}}\n",
                    f"{indent}form_data = dict(body_data)\n",
                ]
            )
            for name in body.binary_fields:
                literal = string_literal(name)
                lines.extend(
                    [
                        f"{indent}if {literal} in form_data:\n",
                        f"{indent}    files[{literal}] = form_data.pop({literal})\n",
                    ]
                )
            lines.append(
                f"{indent}body_arguments.update(data=form_data, files=files)\n"
            )
    else:
        lines = [f'{indent}body_arguments["content"] = body\n']
    if _body_needs_content_type(body):
        lines.append(
            f'{indent}headers.setdefault("Content-Type", '
            f"{string_literal(body.media_type)})\n"
        )
    return lines


def _render_required_body(body: Body) -> list[str]:
    if body.kind == "json":
        return [
            f"{_INDENT}json_body = TypeAdapter({body.annotation}).dump_python(\n",
            f'{_INDENT}    body, mode="json", by_alias=True, exclude_none=True\n',
            f"{_INDENT})\n",
        ]
    if body.kind == "form":
        return [
            f"{_INDENT}form_data = TypeAdapter({body.annotation}).dump_python(\n",
            f'{_INDENT}    body, mode="python", by_alias=True, exclude_none=True\n',
            f"{_INDENT})\n",
        ]
    if body.kind == "multipart":
        lines = [
            f"{_INDENT}body_data = TypeAdapter({body.annotation}).dump_python(\n",
            f'{_INDENT}    body, mode="python", by_alias=True, exclude_none=True\n',
            f"{_INDENT})\n",
            f"{_INDENT}form_data = dict(body_data)\n",
            f"{_INDENT}files: dict[str, bytes] = {{}}\n",
        ]
        for name in body.binary_fields:
            literal = string_literal(name)
            lines.extend(
                [
                    f"{_INDENT}if {literal} in form_data:\n",
                    f"{_INDENT}    files[{literal}] = form_data.pop({literal})\n",
                ]
            )
        return lines
    return []


def _render_request_arguments(operation: Operation) -> str:
    arguments = [
        f"method=HttpMethods.{operation.method.name}",
        'url=f"{self._base_url}{path}"',
    ]
    if _needs_query(operation):
        arguments.append("params=query")
    arguments.append(
        "headers=headers" if _needs_headers(operation) else "headers=self._headers"
    )
    if _needs_cookies(operation):
        arguments.append("cookies=cookies")
    bodies = _operation_bodies(operation)
    if bodies:
        body = bodies[0]
        if len(bodies) > 1 or not body.required:
            arguments.append("**body_arguments")
        elif body.kind == "json":
            arguments.append("json=json_body")
        elif body.kind == "form":
            arguments.append("data=form_data")
        elif body.kind == "multipart":
            arguments.extend(("data=form_data", "files=files"))
        else:
            arguments.append("content=body")
    arguments.append("timeout=self._timeout if timeout is None else timeout")
    return ",\n            ".join(arguments)


def _render_response_handling(responses: Sequence[Response]) -> str:
    lines: list[str] = []
    for response in responses:
        lines.append(f"        {_response_condition(response.status)}:\n")
        contents = _response_contents(response)
        if len(contents) <= 1:
            expression = _response_expression(contents[0]) if contents else "None"
            result = _response_result(response, expression, " " * 12)
            if response.success:
                lines.append(f"            return {result}\n")
                continue
            lines.append(f"            parsed_body = {result}\n")
        else:
            lines.extend(_render_content_response(contents))
            result = _response_result(response, "parsed_body", " " * 12)
            if response.success:
                lines.append(f"            return {result}\n")
                continue
        if not response.success:
            lines.append(
                _wrap(
                    "raise ApiError(response.status_code, response.text, "
                    "parsed_body, response)",
                    " " * 12,
                )
            )
    return "".join(lines)


def _response_result(response: Response, body: str, indent: str) -> str:
    if response.result_annotation is None:
        return body
    nested = f"{indent}    "
    lines = [f"{response.result_annotation}(", f"{nested}body={body},"]
    for header in response.headers:
        key = string_literal(header.wire_name)
        if header.annotation == "str":
            lines.append(f"{nested}{header.name}=response.headers.get({key}),")
            continue
        value = f"response.headers[{key}]"
        if header.annotation.startswith("list["):
            value += '.split(",")'
        lines.extend(
            [
                f"{nested}{header.name}=(",
                f"{nested}    TypeAdapter({header.annotation}).validate_python(",
                f"{nested}        {value}",
                f"{nested}    )",
                f"{nested}    if {key} in response.headers",
                f"{nested}    else None",
                f"{nested}),",
            ]
        )
    lines.append(f"{indent})")
    return "\n".join(lines)


def _render_content_response(contents: Sequence[ResponseContent]) -> list[str]:
    lines = [
        (
            "            response_content_type = "
            'response.headers.get("Content-Type", "")\n'
        ),
        (
            "            response_content_type = "
            'response_content_type.split(";", 1)[0].lower()\n'
        ),
    ]
    for index, content in enumerate(contents):
        keyword = "if" if index == 0 else "elif"
        normalized = content.media_type.split(";", 1)[0].strip().lower()
        lines.extend(
            [
                (
                    f"            {keyword} response_content_type == "
                    f"{string_literal(normalized)}:\n"
                ),
                f"                parsed_body = {_response_expression(content)}\n",
            ]
        )
    lines.extend(
        [
            "            else:\n",
            "                raise ApiError(\n",
            "                    response.status_code,\n",
            (
                '                    f"unsupported response Content-Type: '
                '{response_content_type}",\n'
            ),
            "                    response=response,\n",
            "                )\n",
        ]
    )
    return lines


def _response_condition(status: int | str) -> str:
    if isinstance(status, int):
        return f"if response.status_code == {status}"
    if status == "DEFAULT":
        return "if True"
    lower = int(status[0]) * 100
    return f"if {lower} <= response.status_code < {lower + 100}"


def _response_contents(response: Response) -> tuple[ResponseContent, ...]:
    if response.contents:
        return response.contents
    if response.kind == "empty" or response.annotation == "None":
        return ()
    return (
        ResponseContent(
            annotation=response.annotation,
            model_annotation=response.model_annotation,
            kind=response.kind,
            media_type=response.media_type or "application/json",
        ),
    )


def _response_expression(response: ResponseContent) -> str:
    if response.annotation == "None":
        return "None"
    if response.kind == "binary":
        return "response.content"
    if response.kind == "text":
        return "response.text"
    if response.model_annotation:
        return f"{response.model_annotation}.model_validate(response.json())"
    return f"TypeAdapter({response.annotation}).validate_python(response.json())"


def _accept_header(operation: Operation) -> str:
    accepted = dict.fromkeys(
        content.media_type
        for response in operation.responses
        for content in _response_contents(response)
    )
    return ", ".join(accepted)


def _content_type_header(operation: Operation) -> str:
    bodies = _operation_bodies(operation)
    if len(bodies) != 1:
        return ""
    body = bodies[0]
    if (
        body is None
        or body.kind in {"form", "multipart"}
        or body.media_type.split(";", 1)[0].lower() == "application/json"
    ):
        return ""
    return body.media_type


def _needs_query(operation: Operation) -> bool:
    return bool(query_parameters(operation)) or _security_uses(operation, "query")


def _needs_headers(operation: Operation) -> bool:
    return bool(
        _by_location(operation, "header")
        or _accept_header(operation)
        or _content_type_header(operation)
        or any(_body_needs_content_type(body) for body in _operation_bodies(operation))
        or _security_uses(operation, "header")
    )


def _needs_cookies(operation: Operation) -> bool:
    return bool(_by_location(operation, "cookie")) or _security_uses(
        operation, "cookie"
    )


def _by_location(operation: Operation, location: str) -> tuple[Parameter, ...]:
    return tuple(item for item in operation.parameters if item.location == location)


def _security_uses(operation: Operation, location: str) -> bool:
    required = {name for group in operation.security for name in group}
    return any(
        scheme.name in required and scheme.location == location
        for scheme in operation.security_schemes
    )


def _has_optional_body(operation: Operation) -> bool:
    return operation.body is not None and not operation.body.required


def _operation_bodies(operation: Operation) -> tuple[Body, ...]:
    if operation.bodies:
        return operation.bodies
    return (operation.body,) if operation.body is not None else ()


def _body_needs_content_type(body: Body) -> bool:
    normalized = body.media_type.split(";", 1)[0].strip().lower()
    return body.kind in {"text", "binary"} or (
        body.kind == "json" and normalized != "application/json"
    )


_SERIALIZERS = {
    "path": "serialize_path",
    "query": "serialize_query",
    "header": "serialize_simple",
    "cookie": "serialize_simple",
}


def _serialize_call(parameter: Parameter, value: str) -> str:
    function = _SERIALIZERS[parameter.location]
    arguments = [value]
    if function == "serialize_simple":
        if parameter.explode:
            arguments.append("explode=True")
        return f"{function}({', '.join(arguments)})"

    arguments.insert(0, string_literal(parameter.wire_name))
    default_style = "simple" if parameter.location == "path" else "form"
    default_explode = parameter.location != "path"
    if parameter.style != default_style:
        arguments.append(string_literal(parameter.style))
    if parameter.explode != default_explode:
        arguments.append(f"explode={parameter.explode}")
    if parameter.allow_reserved:
        arguments.append("allow_reserved=True")
    return f"{function}({', '.join(arguments)})"


def _guarded(parameter: Parameter, statement: str) -> str:
    if parameter.required or parameter.default is not NO_DEFAULT:
        return _wrap(statement, _INDENT)
    value = (
        f"params.{parameter.name}" if parameter.location == "query" else parameter.name
    )
    return f"{_INDENT}if {value} is not None:\n" + _wrap(statement, f"{_INDENT}    ")


def _wrap(statement: str, indent: str) -> str:
    if len(indent) + len(statement) <= _LINE_LENGTH:
        return f"{indent}{statement}\n"
    head, _, rest = statement.partition("(")
    inner, _, tail = rest.rpartition(")")
    return f"{indent}{head}(\n{indent}    {inner}\n{indent}){tail}\n"
