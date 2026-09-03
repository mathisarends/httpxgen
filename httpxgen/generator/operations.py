from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from httpxgen.generator.errors import GenerationError
from httpxgen.generator.naming import class_name, identifier
from httpxgen.generator.schema import is_object, schema_type, split_all_of
from httpxgen.openapi import (
    APIParameter,
    APIResponse,
    HttpMethod,
    MediaType,
    OpenAPISpec,
    RequestBody,
    get_operation,
)


@dataclass(frozen=True)
class Parameter:
    name: str
    wire_name: str
    location: str
    annotation: str
    required: bool


@dataclass(frozen=True)
class Response:
    status: int
    annotation: str
    model_annotation: str | None


@dataclass(frozen=True)
class Operation:
    method: HttpMethod
    path: str
    name: str
    parameters: tuple[Parameter, ...]
    body_annotation: str | None
    body_required: bool
    responses: tuple[Response, ...]


def read_operations(spec: OpenAPISpec) -> tuple[Operation, ...]:
    operations: list[Operation] = []
    for path in sorted(spec.paths):
        path_item = spec.paths[path]
        for method in HttpMethod:
            operation = get_operation(path_item, method)
            if operation is None:
                continue
            if not operation.operation_id:
                raise GenerationError(f"{method.upper()} {path} has no operationId")
            body_annotation, body_required = _read_body(operation.request_body)
            operations.append(
                Operation(
                    method=method,
                    path=path,
                    name=identifier(operation.operation_id),
                    parameters=_read_parameters(
                        [*path_item.parameters, *operation.parameters]
                    ),
                    body_annotation=body_annotation,
                    body_required=body_required,
                    responses=_read_responses(
                        operation.responses,
                        method,
                        path,
                        spec.components.schemas,
                    ),
                )
            )

    names = [operation.name for operation in operations]
    if len(names) != len(set(names)):
        raise GenerationError("operationId values must be unique Python identifiers")
    return tuple(operations)


def query_parameters(operation: Operation) -> tuple[Parameter, ...]:
    return tuple(
        parameter for parameter in operation.parameters if parameter.location == "query"
    )


def query_model_name(operation: Operation) -> str:
    return f"{class_name(operation.name)}Params"


def _read_parameters(values: Sequence[APIParameter]) -> tuple[Parameter, ...]:
    parameters: list[Parameter] = []
    for value in values:
        if value.location not in {"path", "query", "header"}:
            raise GenerationError(f"unsupported parameter location: {value.location!r}")
        required = value.required or value.location == "path"
        annotation = schema_type(value.schema_)
        if not required and "None" not in annotation:
            annotation = f"{annotation} | None"
        parameters.append(
            Parameter(
                name=identifier(value.name),
                wire_name=value.name,
                location=value.location,
                annotation=annotation,
                required=required,
            )
        )
    return tuple(parameters)


def _read_body(value: RequestBody | None) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    return schema_type(_json_schema(value.content)), value.required


def _read_responses(
    values: Mapping[str, APIResponse],
    method: HttpMethod,
    path: str,
    schemas: Mapping[str, Any],
) -> tuple[Response, ...]:
    responses: list[Response] = []
    for status_text, response in values.items():
        if not status_text.isdigit() or not 200 <= int(status_text) < 300:
            continue
        schema = _json_schema(response.content) if response.content else None
        responses.append(
            Response(
                status=int(status_text),
                annotation="None" if not schema else schema_type(schema),
                model_annotation=_response_model(schema, schemas),
            )
        )
    if not responses:
        raise GenerationError(f"{method.upper()} {path} has no explicit 2xx response")
    return tuple(sorted(responses, key=lambda response: response.status))


def _response_model(
    schema: Mapping[str, Any] | None,
    schemas: Mapping[str, Any],
) -> str | None:
    if not schema or "$ref" not in schema:
        return None
    name = schema["$ref"].rsplit("/", 1)[-1]
    bases, own_schema = split_all_of(schemas.get(name, {}))
    return class_name(name) if bases or is_object(own_schema) else None


def _json_schema(content: Mapping[str, MediaType]) -> Mapping[str, Any]:
    media = content.get("application/json")
    if media is None or media.schema_ is None:
        raise GenerationError("only application/json bodies are supported")
    return media.schema_
