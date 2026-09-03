import re
from collections.abc import Mapping, Sequence
from typing import Any

from httpxgen.generator.naming import (
    class_name,
    identifier,
    string_literal,
    used_names,
)
from httpxgen.generator.operations import (
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
    supporting_types = _render_http_method(operations)
    methods = "\n\n".join(_render_operation(operation) for operation in operations)
    if not methods:
        methods = "    pass"
    annotations = " ".join(
        [
            *(
                parameter.annotation
                for operation in operations
                for parameter in operation.parameters
            ),
            *(operation.body_annotation or "" for operation in operations),
            *(
                response.annotation
                for operation in operations
                for response in operation.responses
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


def _render_http_method(operations: Sequence[Operation]) -> str:
    methods = sorted({operation.method for operation in operations})
    if not methods:
        return ""
    members = "\n".join(f'    {method.name} = "{method.upper()}"' for method in methods)
    return f"class _HttpMethod(StrEnum):\n{members}"


def _render_client_imports(
    operations: Sequence[Operation], annotations: str, model_names: Sequence[str]
) -> str:
    lines = ["from collections.abc import Mapping"]
    if operations:
        lines.append("from enum import StrEnum")
    datetime_names = used_names(annotations, ("date", "datetime"))
    if datetime_names:
        lines.append(f"from datetime import {', '.join(datetime_names)}")
    typing_names = used_names(annotations, ("Any", "Literal"))
    has_parameter_mappings = any(
        parameter.location == "header"
        for operation in operations
        for parameter in operation.parameters
    )
    if has_parameter_mappings and "Any" not in typing_names:
        typing_names.insert(0, "Any")
    typing_names.append("Self")
    if typing_names:
        lines.append(f"from typing import {', '.join(typing_names)}")
    if "UUID" in annotations:
        lines.append("from uuid import UUID")
    lines.extend(["", "import httpx"])
    pydantic_names: list[str] = []
    needs_type_adapter = any(
        operation.body_annotation for operation in operations
    ) or any(
        response.annotation != "None" and response.model_annotation is None
        for operation in operations
        for response in operation.responses
    )
    if needs_type_adapter:
        pydantic_names.append("TypeAdapter")
    if pydantic_names:
        lines.append(f"from pydantic import {', '.join(pydantic_names)}")
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
        default = "" if parameter.required else " = None"
        arguments.append(
            (f"{parameter.name}: {parameter.annotation}{default}", parameter.required)
        )
    if operation.body_annotation:
        default = "" if operation.body_required else " = None"
        annotation = operation.body_annotation
        if not operation.body_required and "None" not in annotation:
            annotation += " | None"
        arguments.append((f"body: {annotation}{default}", operation.body_required))
    arguments.sort(key=lambda item: not item[1])
    signature = "\n".join(f"        {value}," for value, _ in arguments)
    if signature:
        signature += "\n"
    return_annotation = " | ".join(
        dict.fromkeys(item.annotation for item in operation.responses)
    )
    path_source = re.sub(
        r"\{([^}]+)\}",
        lambda match: "{" + identifier(match.group(1)) + "}",
        operation.path,
    )
    url = f'f"{{self._base_url}}{path_source}"'

    query_items = query_parameters(operation)
    header_items = [item for item in operation.parameters if item.location == "header"]
    headers = _render_mapping("headers", header_items, base="self._headers")
    query = _render_query_assignment(operation, query_items)
    body = _render_body_assignment(operation)
    request_args = [
        f"method=_HttpMethod.{operation.method.name}",
        f"url={url}",
    ]
    if query_items:
        request_args.append(
            'params=params.model_dump(mode="json", by_alias=True, exclude_none=True)'
        )
    request_args.append("headers=headers" if header_items else "headers=self._headers")
    if operation.body_annotation:
        request_args.append("json=json_body")
    request_args.append("timeout=self._timeout if timeout is None else timeout")
    request = ",\n            ".join(request_args)
    return render_template(
        TemplateName.OPERATION,
        operation=operation,
        signature=signature,
        return_annotation=return_annotation,
        query_assignment=query,
        header_mapping=headers,
        body_assignment=body,
        request_arguments=request,
        response_handling=_render_response_handling(operation.responses),
    ).rstrip("\n")


def _render_query_assignment(
    operation: Operation,
    parameters: Sequence[Parameter],
) -> str:
    if not parameters:
        return ""
    fields = "\n".join(
        f"            {parameter.name}={parameter.name}," for parameter in parameters
    )
    return f"        params = {query_model_name(operation)}(\n{fields}\n        )\n"


def _render_body_assignment(operation: Operation) -> str:
    if operation.body_annotation is None:
        return ""
    if operation.body_required:
        return (
            f"        json_body = TypeAdapter({operation.body_annotation}).dump_python(\n"
            '            body, mode="json", by_alias=True, exclude_none=True\n'
            "        )\n"
        )
    return (
        "        json_body = (\n"
        f"            TypeAdapter({operation.body_annotation}).dump_python(\n"
        '                body, mode="json", by_alias=True, exclude_none=True\n'
        "            )\n"
        "            if body is not None\n"
        "            else None\n"
        "        )\n"
    )


def _render_mapping(
    name: str,
    parameters: Sequence[Parameter],
    *,
    base: str | None = None,
) -> str:
    if not parameters:
        return ""
    initial = f"dict({base})" if base else "{}"
    lines = [f"        {name}: dict[str, Any] = {initial}\n"]
    for parameter in parameters:
        if parameter.required:
            lines.append(
                f"        {name}[{string_literal(parameter.wire_name)}] = {parameter.name}\n"
            )
        else:
            lines.append(f"        if {parameter.name} is not None:\n")
            lines.append(
                f"            {name}[{string_literal(parameter.wire_name)}] = {parameter.name}\n"
            )
    return "".join(lines)


def _render_response_handling(responses: Sequence[Response]) -> str:
    lines: list[str] = []
    for response in responses:
        lines.append(f"        if response.status_code == {response.status}:\n")
        if response.annotation == "None":
            lines.append("            return None\n")
        elif response.model_annotation is not None:
            lines.append(
                f"            return {response.model_annotation}.model_validate("
                "response.json())\n"
            )
        else:
            lines.append(
                f"            return TypeAdapter({response.annotation}).validate_python("
                "response.json())\n"
            )
    return "".join(lines)
