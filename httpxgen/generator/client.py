import re
from collections.abc import Mapping, Sequence
from typing import Any

from httpxgen.generator.naming import (
    class_name,
    identifier,
    string_literal,
    used_names,
)
from httpxgen.generator.operations import Operation, Parameter, Response
from httpxgen.generator.schema import ordered_schemas
from httpxgen.generator.templates import TemplateName, render_template


def render_client(
    operations: Sequence[Operation], schemas: Mapping[str, Any], client_name: str
) -> str:
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
    model_names = [
        class_name(name)
        for name in ordered_schemas(schemas)
        if re.search(rf"\b{re.escape(class_name(name))}\b", annotations)
    ]
    imports = _render_client_imports(operations, annotations, model_names)
    return render_template(
        TemplateName.CLIENT,
        imports=imports,
        client_name=client_name,
        methods=methods,
    )


def _render_client_imports(
    operations: Sequence[Operation], annotations: str, model_names: Sequence[str]
) -> str:
    lines = ["from collections.abc import Mapping"]
    datetime_names = used_names(annotations, ("date", "datetime"))
    if datetime_names:
        lines.append(f"from datetime import {', '.join(datetime_names)}")
    typing_names = used_names(annotations, ("Any", "Literal"))
    has_parameter_mappings = any(
        parameter.location in {"query", "header"}
        for operation in operations
        for parameter in operation.parameters
    )
    if has_parameter_mappings and "Any" not in typing_names:
        typing_names.insert(0, "Any")
    if typing_names:
        lines.append(f"from typing import {', '.join(typing_names)}")
    if "UUID" in annotations:
        lines.append("from uuid import UUID")
    lines.extend(["", "import httpx"])
    needs_type_adapter = any(
        operation.body_annotation for operation in operations
    ) or any(
        response.annotation != "None" and response.model_annotation is None
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
    path_prefix = "f" if "{" in path_source else ""
    path_assignment = f'        path = {path_prefix}"{path_source}"\n'
    wrapped_path = f'            {path_prefix}"{path_source}"'
    if len(path_assignment.rstrip()) > 88 and len(wrapped_path) <= 88:
        path_assignment = f"        path = (\n{wrapped_path}\n        )\n"

    query_items = [item for item in operation.parameters if item.location == "query"]
    header_items = [item for item in operation.parameters if item.location == "header"]
    query = _render_mapping("params", query_items)
    headers = _render_mapping("headers", header_items, base="self._headers")
    request_args = [f'"{operation.method.upper()}"', 'f"{self._base_url}{path}"']
    if query_items:
        request_args.append("params=params")
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
        path_assignment=path_assignment,
        query_mapping=query,
        header_mapping=headers,
        has_body=operation.body_annotation is not None,
        request_arguments=request,
        response_handling=_render_response_handling(operation.responses),
    ).rstrip("\n")


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
