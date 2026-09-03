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


class OpenAPIModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class MediaType(OpenAPIModel):
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")


class RequestBody(OpenAPIModel):
    required: bool = False
    content: dict[str, MediaType] = Field(default_factory=dict)


class APIResponse(OpenAPIModel):
    content: dict[str, MediaType] = Field(default_factory=dict)


class APIParameter(OpenAPIModel):
    name: str
    location: str = Field(alias="in")
    required: bool = False
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")


class APIOperation(OpenAPIModel):
    operation_id: str | None = Field(default=None, alias="operationId")
    tags: tuple[str, ...] = ()
    parameters: tuple[APIParameter, ...] = ()
    request_body: RequestBody | None = Field(default=None, alias="requestBody")
    responses: dict[str, APIResponse] = Field(default_factory=dict)


class PathItem(OpenAPIModel):
    parameters: tuple[APIParameter, ...] = ()
    get: APIOperation | None = None
    put: APIOperation | None = None
    post: APIOperation | None = None
    delete: APIOperation | None = None
    options: APIOperation | None = None
    head: APIOperation | None = None
    patch: APIOperation | None = None


class Components(OpenAPIModel):
    schemas: dict[str, dict[str, Any]] = Field(default_factory=dict)


class APIInfo(OpenAPIModel):
    title: str = ""


class OpenAPISpec(OpenAPIModel):
    openapi: str
    info: APIInfo = Field(default_factory=APIInfo)
    paths: dict[str, PathItem]
    components: Components = Field(default_factory=Components)

    @field_validator("openapi")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        if not value.startswith("3."):
            raise ValueError("only OpenAPI 3.x documents are supported")
        return value


def get_operation(path_item: PathItem, method: HttpMethod) -> APIOperation | None:
    return getattr(path_item, method.value)
