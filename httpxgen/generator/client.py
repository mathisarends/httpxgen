import re
from collections.abc import Mapping, Sequence
from typing import Any

from httpxgen.generator.naming import class_name, used_names
from httpxgen.generator.operations import (
    NO_DEFAULT,
    Body,
    Operation,
    Parameter,
    Response,
    query_model_name,
    query_parameters,
)
from httpxgen.generator.schema import ordered_schemas
from httpxgen.generator.templates import TemplateName, render_template


def render_client(
    operations: Sequence[Operation], schemas: Mapping[str, Any], client_name: str
) -> str:
    supporting_types = _render_supporting_types(operations)
    methods = "\n\n".join(_render_operation(operation) for operation in operations)
    if not methods:
        methods = "    pass"
    annotations = " ".join(
        [
            *(item.annotation for op in operations for item in op.parameters),
            *(op.body_annotation or "" for op in operations),
            *(item.annotation for op in operations for item in op.responses),
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
        ]
    )
    imports = _render_client_imports(operations, annotations, model_names)
    return render_template(
        TemplateName.CLIENT,
        imports=imports,
        supporting_types=supporting_types,
        client_name=client_name,
        methods=methods,
    )


def _render_supporting_types(operations: Sequence[Operation]) -> str:
    blocks: list[str] = []
    methods = sorted({operation.method for operation in operations})
    if methods:
        members = "\n".join(
            f'    {method.name} = "{method.upper()}"' for method in methods
        )
        blocks.append(f"class _HttpMethod(StrEnum):\n{members}")
    if any(operation.parameters for operation in operations):
        blocks.append(_PARAMETER_HELPERS)
    schemes = {
        scheme.name: scheme
        for operation in operations
        for scheme in operation.security_schemes
    }
    if any(operation.security for operation in operations):
        definitions = {
            name: (item.kind, item.location, item.parameter_name, item.prefix)
            for name, item in schemes.items()
        }
        blocks.append(f"_SECURITY_SCHEMES = {definitions!r}\n\n{_SECURITY_HELPER}")
    return "\n\n\n".join(blocks)


def _render_client_imports(
    operations: Sequence[Operation], annotations: str, model_names: Sequence[str]
) -> str:
    lines = ["from collections.abc import Mapping"]
    if any(
        scheme.kind == "basic"
        for operation in operations
        for scheme in operation.security_schemes
    ):
        lines.append("from base64 import b64encode")
    if operations:
        lines.append("from enum import Enum, StrEnum")
    if any(operation.parameters for operation in operations):
        lines.append("from urllib.parse import quote")
    datetime_names = used_names(annotations, ("date", "datetime"))
    if datetime_names:
        lines.append(f"from datetime import {', '.join(datetime_names)}")
    typing_names = used_names(annotations, ("Literal",))
    if operations:
        typing_names.insert(0, "Any")
    typing_names.append("Self")
    lines.append(f"from typing import {', '.join(dict.fromkeys(typing_names))}")
    if "UUID" in annotations:
        lines.append("from uuid import UUID")
    lines.extend(["", "import httpx"])
    needs_type_adapter = any(operation.body for operation in operations) or any(
        response.annotation not in {"None", "bytes", "str"}
        for operation in operations
        for response in operation.responses
    )
    if needs_type_adapter:
        lines.append("from pydantic import TypeAdapter")
    lines.extend(["", "from .exceptions import ApiError"])
    if model_names:
        model_import = f"from .models import {', '.join(model_names)}"
        if len(model_import) <= 88:
            lines.append(model_import)
        else:
            lines.extend(
                [
                    "from .models import (",
                    *(f"    {name}," for name in model_names),
                    ")",
                ]
            )
    return "\n".join(lines)


def _render_operation(operation: Operation) -> str:
    arguments: list[tuple[str, bool]] = []
    for parameter in operation.parameters:
        default = _parameter_default(parameter)
        arguments.append(
            (f"{parameter.name}: {parameter.annotation}{default}", parameter.required)
        )
    if operation.body_annotation:
        default = "" if operation.body_required else " = None"
        annotation = operation.body_annotation
        if not operation.body_required:
            annotation = f"{annotation} | None"
        arguments.append((f"body: {annotation}{default}", operation.body_required))
    arguments.sort(key=lambda item: not item[1])
    signature = "\n".join(f"        {value}," for value, _ in arguments)
    if signature:
        signature += "\n"
    successes = [item.annotation for item in operation.responses if item.success]
    return_annotation = " | ".join(dict.fromkeys(successes))

    assignments = _render_parameter_assignments(operation)
    assignments += _render_security(operation)
    assignments += _render_body_assignment(operation)
    request_args = [
        f"method=_HttpMethod.{operation.method.name}",
        'url=f"{self._base_url}{path}"',
    ]
    if (
        any(item.location == "query" for item in operation.parameters)
        or operation.security
    ):
        request_args.append("params=query")
    needs_headers = (
        any(item.location == "header" for item in operation.parameters)
        or bool(operation.security)
        or any(item.media_type for item in operation.responses)
        or (
            _operation_body(operation) is not None
            and _operation_body(operation).kind in {"binary", "text"}
        )
    )
    if needs_headers:
        request_args.append("headers=headers")
    else:
        request_args.append("headers=self._headers")
    if any(
        item.location == "cookie" for item in operation.parameters
    ) or _security_uses(operation, "cookie"):
        request_args.append("cookies=cookies")
    if _operation_body(operation):
        request_args.append("**body_arguments")
    request_args.append("timeout=self._timeout if timeout is None else timeout")
    request = ",\n            ".join(request_args)
    return render_template(
        TemplateName.OPERATION,
        operation=operation,
        signature=signature,
        return_annotation=return_annotation,
        assignments=assignments,
        request_arguments=request,
        response_handling=_render_response_handling(operation.responses),
    ).rstrip("\n")


def _parameter_default(parameter: Parameter) -> str:
    if parameter.default is not NO_DEFAULT:
        return f" = {parameter.default_source or repr(parameter.default)}"
    return "" if parameter.required else " = None"


def _render_parameter_assignments(operation: Operation) -> str:
    lines = [f"        path = {operation.path!r}\n"]
    has_query = any(item.location == "query" for item in operation.parameters)
    has_headers = (
        any(item.location == "header" for item in operation.parameters)
        or (
            _operation_body(operation) is not None
            and _operation_body(operation).kind in {"binary", "text"}
        )
        or any(item.media_type for item in operation.responses)
    )
    has_cookies = any(item.location == "cookie" for item in operation.parameters)
    if has_query or operation.security:
        lines.append("        query: list[tuple[str, str]] = []\n")
    if has_headers or operation.security:
        lines.append("        headers = dict(self._headers)\n")
    if has_cookies or operation.security:
        lines.append("        cookies: dict[str, str] = {}\n")
    accepted = list(
        dict.fromkeys(
            item.media_type
            for item in operation.responses
            if item.media_type is not None
        )
    )
    if accepted:
        lines.append(f"        headers.setdefault('Accept', {', '.join(accepted)!r})\n")
    query_items = query_parameters(operation)
    if query_items:
        lines.append(f"        params = {query_model_name(operation)}(\n")
        lines.extend(f"            {item.name}={item.name},\n" for item in query_items)
        lines.append("        )\n")
    for item in operation.parameters:
        value = f"params.{item.name}" if item.location == "query" else item.name
        indent = ""
        if not item.required and item.default is NO_DEFAULT:
            lines.append(f"        if {value} is not None:\n")
            indent = "    "
        if item.location == "path":
            expression = (
                f"_serialize_path({item.wire_name!r}, {value}, {item.style!r}, "
                f"{item.explode!r}, {item.allow_reserved!r})"
            )
            lines.append(
                f"        {indent}path = path.replace({('{' + item.wire_name + '}')!r}, {expression})\n"
            )
        elif item.location == "query":
            lines.append(
                f"        {indent}query.extend(_serialize_query({item.wire_name!r}, "
                f"{value}, {item.style!r}, {item.explode!r}))\n"
            )
        elif item.location == "header":
            lines.append(
                f"        {indent}headers[{item.wire_name!r}] = "
                f"_serialize_simple({value}, {item.explode!r})\n"
            )
        else:
            lines.append(
                f"        {indent}cookies[{item.wire_name!r}] = "
                f"_serialize_simple({value}, {item.explode!r})\n"
            )
    return "".join(lines) + "\n"


def _render_security(operation: Operation) -> str:
    if not operation.security:
        return ""
    return (
        "        _apply_security(\n"
        f"            self._credentials, {operation.security!r}, headers, query, cookies\n"
        "        )\n\n"
    )


def _security_uses(operation: Operation, location: str) -> bool:
    required_names = {name for group in operation.security for name in group}
    return any(
        scheme.name in required_names and scheme.location == location
        for scheme in operation.security_schemes
    )


def _render_body_assignment(operation: Operation) -> str:
    body = _operation_body(operation)
    if body is None:
        return ""
    lines = ["        body_arguments: dict[str, Any] = {}\n"]
    conditional = not body.required
    if conditional:
        lines.append("        if body is not None:\n")
    indent = "            " if conditional else "        "
    if body.kind == "json":
        lines.append(
            f"{indent}body_arguments['json'] = TypeAdapter({body.annotation}).dump_python(\n"
            f"{indent}    body, mode='json', by_alias=True, exclude_none=True\n"
            f"{indent})\n"
        )
    elif body.kind in {"form", "multipart"}:
        lines.append(
            f"{indent}body_data = TypeAdapter({body.annotation}).dump_python(\n"
            f"{indent}    body, mode='python', by_alias=True, exclude_none=True\n"
            f"{indent})\n"
        )
        if body.kind == "form":
            lines.append(f"{indent}body_arguments['data'] = body_data\n")
        else:
            lines.append(f"{indent}files = {{}}\n")
            lines.append(f"{indent}form = dict(body_data)\n")
            for name in body.binary_fields:
                lines.append(f"{indent}if {name!r} in form:\n")
                lines.append(f"{indent}    files[{name!r}] = form.pop({name!r})\n")
            lines.append(f"{indent}body_arguments.update(data=form, files=files)\n")
    else:
        lines.append(f"{indent}body_arguments['content'] = body\n")
        lines.append(
            f"{indent}headers.setdefault('Content-Type', {body.media_type!r})\n"
        )
    return "".join(lines) + "\n"


def _operation_body(operation: Operation) -> Body | None:
    if operation.body is not None:
        return operation.body
    if operation.body_annotation is None:
        return None
    return Body(
        operation.body_annotation,
        operation.body_required,
        "application/json",
        "json",
    )


def _render_response_handling(responses: Sequence[Response]) -> str:
    lines: list[str] = []
    for response in responses:
        condition = _response_condition(response.status)
        lines.append(f"        {condition}:\n")
        expression = _response_expression(response)
        if response.success:
            lines.append(f"            return {expression}\n")
        else:
            lines.append(
                "            raise ApiError(\n"
                f"                response.status_code, response.text, {expression}, response\n"
                "            )\n"
            )
    return "".join(lines)


def _response_condition(status: int | str) -> str:
    if isinstance(status, int):
        return f"if response.status_code == {status}"
    if status == "DEFAULT":
        return "if True"
    lower = int(status[0]) * 100
    upper = lower + 100
    return f"if {lower} <= response.status_code < {upper}"


def _response_expression(response: Response) -> str:
    if response.kind == "empty" or response.annotation == "None":
        return "None"
    if response.kind == "binary":
        return "response.content"
    if response.kind == "text":
        return "response.text"
    if response.model_annotation:
        return f"{response.model_annotation}.model_validate(response.json())"
    return f"TypeAdapter({response.annotation}).validate_python(response.json())"


_PARAMETER_HELPERS = """\
def _scalar(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _serialize_simple(value: Any, explode: bool) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, Mapping):
        if explode:
            return ",".join(f"{_scalar(key)}={_scalar(item)}" for key, item in value.items())
        return ",".join(_scalar(item) for pair in value.items() for item in pair)
    if isinstance(value, (list, tuple)):
        return ",".join(_scalar(item) for item in value)
    return _scalar(value)


def _serialize_query(
    name: str, value: Any, style: str, explode: bool
) -> list[tuple[str, str]]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if style == "deepObject" and isinstance(value, Mapping):
        return [(f"{name}[{key}]", _scalar(item)) for key, item in value.items()]
    if isinstance(value, Mapping) and style == "form" and explode:
        return [(_scalar(key), _scalar(item)) for key, item in value.items()]
    if isinstance(value, (list, tuple)) and style == "form" and explode:
        return [(name, _scalar(item)) for item in value]
    delimiter = " " if style == "spaceDelimited" else "|" if style == "pipeDelimited" else ","
    if isinstance(value, Mapping):
        rendered = delimiter.join(_scalar(item) for pair in value.items() for item in pair)
    elif isinstance(value, (list, tuple)):
        rendered = delimiter.join(_scalar(item) for item in value)
    else:
        rendered = _scalar(value)
    return [(name, rendered)]


def _serialize_path(
    name: str, value: Any, style: str, explode: bool, allow_reserved: bool
) -> str:
    rendered = _serialize_simple(value, explode)
    safe = ":/?#[]@!$&'()*+,;=" if allow_reserved else ""
    rendered = quote(rendered, safe=safe)
    if style == "label":
        return f".{rendered}"
    if style == "matrix":
        return f";{name}={rendered}"
    return rendered"""


_SECURITY_HELPER = """\
def _apply_security(
    credentials: Mapping[str, str | tuple[str, str]],
    requirements: tuple[tuple[str, ...], ...],
    headers: dict[str, str],
    query: list[tuple[str, str]],
    cookies: dict[str, str],
) -> None:
    selected = next(
        (requirement for requirement in requirements if all(name in credentials for name in requirement)),
        None,
    )
    if selected is None:
        choices = " or ".join(" + ".join(item) for item in requirements)
        raise ValueError(f"missing credentials for {choices}")
    for name in selected:
        kind, location, parameter_name, prefix = _SECURITY_SCHEMES[name]
        credential = credentials[name]
        if kind == "basic":
            if not isinstance(credential, tuple):
                raise TypeError(f"credential {name!r} must be a (username, password) tuple")
            raw = f"{credential[0]}:{credential[1]}".encode()
            value = f"Basic {b64encode(raw).decode()}"
        else:
            if not isinstance(credential, str):
                raise TypeError(f"credential {name!r} must be a string")
            value = f"{prefix} {credential}" if prefix else credential
        if location == "header":
            headers[parameter_name] = value
        elif location == "query":
            query.append((parameter_name, value))
        else:
            cookies[parameter_name] = value"""
