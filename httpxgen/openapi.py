import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HttpMethod(StrEnum):
    GET = "get"
    PUT = "put"
    POST = "post"
    DELETE = "delete"
    OPTIONS = "options"
    HEAD = "head"
    PATCH = "patch"
    TRACE = "trace"


class OpenAPIModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class MediaType(OpenAPIModel):
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")


class RequestBody(OpenAPIModel):
    required: bool = False
    content: dict[str, MediaType] = Field(default_factory=dict)


class Reference(OpenAPIModel):
    ref: str = Field(alias="$ref")


class APIHeader(OpenAPIModel):
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
    content: dict[str, MediaType] = Field(default_factory=dict)


class APIResponse(OpenAPIModel):
    content: dict[str, MediaType] = Field(default_factory=dict)
    headers: dict[str, Reference | APIHeader] = Field(default_factory=dict)


class APIParameter(OpenAPIModel):
    name: str
    location: str = Field(alias="in")
    required: bool = False
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
    content: dict[str, MediaType] = Field(default_factory=dict)
    style: str | None = None
    explode: bool | None = None
    allow_reserved: bool = Field(default=False, alias="allowReserved")


class APIOperation(OpenAPIModel):
    operation_id: str | None = Field(default=None, alias="operationId")
    tags: tuple[str, ...] = ()
    parameters: tuple[APIParameter | Reference, ...] = ()
    request_body: RequestBody | Reference | None = Field(
        default=None, alias="requestBody"
    )
    responses: dict[str, APIResponse | Reference] = Field(default_factory=dict)
    security: tuple[dict[str, list[str]], ...] | None = None


class PathItem(OpenAPIModel):
    ref: str | None = Field(default=None, alias="$ref")
    parameters: tuple[APIParameter | Reference, ...] = ()
    get: APIOperation | None = None
    put: APIOperation | None = None
    post: APIOperation | None = None
    delete: APIOperation | None = None
    options: APIOperation | None = None
    head: APIOperation | None = None
    patch: APIOperation | None = None
    trace: APIOperation | None = None


class Components(OpenAPIModel):
    schemas: dict[str, dict[str, Any]] = Field(default_factory=dict)
    parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    request_bodies: dict[str, dict[str, Any]] = Field(
        default_factory=dict, alias="requestBodies"
    )
    responses: dict[str, dict[str, Any]] = Field(default_factory=dict)
    headers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    path_items: dict[str, dict[str, Any]] = Field(
        default_factory=dict, alias="pathItems"
    )
    security_schemes: dict[str, dict[str, Any]] = Field(
        default_factory=dict, alias="securitySchemes"
    )


class APIInfo(OpenAPIModel):
    title: str = ""


class OpenAPISpec(OpenAPIModel):
    openapi: str
    info: APIInfo = Field(default_factory=APIInfo)
    paths: dict[str, PathItem]
    components: Components = Field(default_factory=Components)
    security: tuple[dict[str, list[str]], ...] = ()

    @field_validator("openapi")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        if not re.fullmatch(r"3\.(0|1)\.\d+(?:[-+].+)?", value):
            raise ValueError("only OpenAPI 3.0 and 3.1 documents are supported")
        return value


def get_operation(path_item: PathItem, method: HttpMethod) -> APIOperation | None:
    return getattr(path_item, method.value)
