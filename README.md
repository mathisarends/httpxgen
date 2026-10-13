# httpxgen

> **OpenAPI in. Typed async Python out.**

`httpxgen` turns an OpenAPI 3 document into a readable, fully typed async
Python client built for [httpx](https://www.python-httpx.org/) and
[Pydantic](https://docs.pydantic.dev/). The generated source looks like code
you would write yourself: real method signatures, idiomatic names, explicit
request handling, and models your editor understands.

```sh
httpxgen openapi.yaml src/payments --package-name payments
```

There is no runtime framework, reflection, or hidden request machinery. Generate
the client, check it into your repository, review it, debug it, and ship it.

## Contents

- [Why httpxgen?](#why-httpxgen)
- [Generated package](#generated-package)
- [Install](#install)
- [Quick start](#quick-start)
- [From OpenAPI to Python](#from-openapi-to-python)
- [CLI reference](#cli-reference)
- [Automation and CI](#automation-and-ci)
- [Supported scope](#supported-scope)
- [Development](#development)
- [License](#license)

## Why httpxgen?

| You get | Why it matters |
| --- | --- |
| Plain, generated Python | Read, review, and debug every request without learning a runtime abstraction |
| Precise async methods | `operationId` becomes an idiomatic method with real path, query, header, and body parameters |
| Pydantic 2 models | Validation, aliases, constraints, recursive types, `allOf`, and discriminated unions stay useful in Python |
| Native Python types | OpenAPI formats become types such as `UUID`, `datetime`, `StrEnum`, and `Literal` |
| Explicit error handling | Transport failures, invalid responses, and API errors are separate typed exceptions |
| Flexible transport | Use `httpx.AsyncClient` or any compatible async client through a structural protocol |
| Deterministic output | Commit generated files and use `--check` to catch stale clients in CI |
| Tag-based packages | Split a large API into focused clients while generating shared code only once |

`httpxgen` is a build-time tool. Your generated package depends on Pydantic for
its models, but it does **not** depend on `httpxgen` at runtime.

## Generated package

A regular specification becomes a self-contained Python package:

```
openapi.json  ──▶  httpxgen  ──▶  payments/
                                    ├── __init__.py
                                    ├── client.py         # the public client class
                                    ├── models.py
                                    ├── exceptions.py     # generated client errors
                                    ├── http_methods.py   # HttpMethods
                                    ├── serialization.py  # parameter and auth helpers
                                    ├── transport.py      # structural protocols and file types
                                    └── py.typed
```

For larger specifications, repeat `--tag` to create focused subclients. Shared
models and support modules are generated once beside them:

```
openapi.json  ──▶  httpxgen  ──▶  api/
                                    ├── __init__.py       # clients, ApiError, all models
                                    ├── shared/           # generated once
                                    │     ├── exceptions.py
                                    │     ├── http_methods.py
                                    │     ├── models.py   # only models used by both tags
                                    │     ├── serialization.py
                                    │     └── transport.py
                                    ├── payments/
                                    │     ├── client.py
                                    │     └── models.py   # models only payments uses
                                    ├── invoices/
                                    │     ├── client.py
                                    │     └── models.py
                                    └── py.typed
```

## Install

Requires Python 3.12 or newer.

With [uv](https://docs.astral.sh/uv/):

```sh
uv tool install httpxgen      # standalone CLI
uv add --dev httpxgen         # dev dependency of your project
```

With pip:

```sh
pip install httpxgen
```

Or run it without installing anything:

```sh
uvx httpxgen openapi.json src/payments
```

## Quick start

Generate a package from a local OpenAPI JSON or YAML document:

```sh
httpxgen openapi.yaml src/payments --package-name payments
```

```
Generated 8 file(s) in package src/payments.
```

```python
import asyncio

import httpx

from payments import (
    CardPaymentMethod,
    ClientError,
    CreateChargeRequest,
    Money,
    PaymentsClient,
)


async def main() -> None:
    async with httpx.AsyncClient() as http_client:
        client = PaymentsClient(
            http_client,
            "https://payments.example.com/api",
            credentials={"bearerAuth": "your-token"},
        )
        page = await client.list_charges(status="succeeded", page_size=50)
        for charge in page.items:
            print(charge.id, charge.amount.amount_cents, charge.status)

        try:
            charge = await client.create_charge(
                CreateChargeRequest(
                    amount=Money(amount_cents=4200, currency="EUR"),
                    payment_method=CardPaymentMethod(...),
                )
            )
        except ClientError as error:
            print(f"payment request failed: {error}")


asyncio.run(main())
```

The package root re-exports the client, models, and exceptions, so application
imports stay short and stable.

## From OpenAPI to Python

### OpenAPI input

```yaml
/charges:
  get:
    operationId: listCharges
    parameters:
      - name: status
        in: query
        schema: { $ref: "#/components/schemas/ChargeStatus" }
      - name: cursor
        in: query
        schema: { type: string }
      - name: page_size
        in: query
        schema: { type: integer, default: 25, minimum: 1, maximum: 200 }
    responses:
      "200":
        content:
          application/json:
            schema: { $ref: "#/components/schemas/ChargePage" }
```

### Generated client

`operationId` becomes an idiomatic snake_case method, optional query parameters are only sent when set, and the response is validated into a model:

`client.py` holds nothing but the imports and the client class — the serialization
helpers live in `serialization.py`, the error type in `exceptions.py`:

```python
class ListChargesParams(BaseModel):
    status: ChargeStatus | None = None
    cursor: str | None = None
    page_size: int = Field(25, ge=1, le=200)


class PaymentsClient:
    async def list_charges(
        self,
        status: ChargeStatus | None = None,
        cursor: str | None = None,
        page_size: int = 25,
        *,
        timeout: float | None = None,
    ) -> ChargePage:
        path = "/charges"

        params = ListChargesParams(
            status=status,
            cursor=cursor,
            page_size=page_size,
        )
        query: list[tuple[str, str]] = []
        if params.status is not None:
            query.extend(serialize_query("status", params.status))
        if params.cursor is not None:
            query.extend(serialize_query("cursor", params.cursor))
        query.extend(serialize_query("page_size", params.page_size))

        headers = dict(self._headers)
        headers.setdefault("Accept", "application/json")

        apply_security(self._credentials, [("bearerAuth",)], headers, query, {})

        try:
            response = await self._client.request(
                method=HttpMethods.GET,
                url=f"{self._base_url}{path}",
                params=query,
                headers=headers,
                timeout=self._timeout if timeout is None else timeout,
            )
        except Exception as error:
            raise TransportError(error) from error

        try:
            if response.status_code == 200:
                return ChargePage.model_validate(response.json())
            raise ApiError(response.status_code, response.text, response=response)
        except ClientError:
            raise
        except Exception as error:
            raise ResponseValidationError(
                response.status_code, response, error
            ) from error
```

Path parameters carry their spec format — `format: uuid` becomes `UUID`, not `str`:

```python
    async def get_customer(
        self,
        customer_id: UUID,
        *,
        timeout: float | None = None,
    ) -> Customer:
        path = "/customers/{customerId}"
        path = path.replace("{customerId}", serialize_path("customerId", customer_id))

        headers = dict(self._headers)
        headers.setdefault("Accept", "application/json")

        response = await self._client.request(
            method=HttpMethods.GET,
            url=f"{self._base_url}{path}",
            headers=headers,
            timeout=self._timeout if timeout is None else timeout,
        )

        if response.status_code == 200:
            return Customer.model_validate(response.json())
        if response.status_code == 404:
            detail = ApiErrorModel.model_validate(response.json())
            raise ApiError(response.status_code, response.text, detail, response)

        raise ApiError(response.status_code, response.text, response=response)
```

Request bodies are a single typed `body` argument, serialized by alias.
JSON inputs are validated using the declared Pydantic schema before the HTTP
transport runs, including mappings and model instances changed after creation.
Invalid inputs raise `RequestValidationError`; Pydantic's normal accepted
conversions apply before serialization.
Unsupported runtime `content_type` choices also raise `RequestValidationError`
before sending a request, with the declared alternatives listed.
Explicitly supplied nullable fields are sent as JSON null; unset nullable fields
are omitted, including inside nested models:

For `application/merge-patch+json`, all unset model fields are omitted, including
schema defaults. Explicit values equal to a default are still sent. Ordinary
JSON create requests continue to include non-null defaults.

Omit an optional JSON body by leaving out `body`. Passing `body=None` sends the
literal JSON payload `null` when the schema permits null, with the selected JSON
Content-Type. Omission uses a separate generated sentinel.

```python
    async def create_charge(
        self,
        body: CreateChargeRequest,
        *,
        timeout: float | None = None,
    ) -> Charge:
        ...
        json_body = serialize_json_body(body, CreateChargeRequest)
        ...
```

The same direct shape is used for JSON, form, text, and small binary bodies.
An `application/octet-stream` body accepts `bytes`, `Iterable[bytes]`, or
`AsyncIterable[bytes]` and is passed directly as `content=`.

Synchronous binary iterables are adapted lazily to async chunks. Exceptions
raised while consuming an upload iterable are reported as `TransportError`.

Multipart fields are flattened into method arguments. Binary arrays become
repeated parts with the same wire name. Parameter and multipart argument names
that collide with generated locals (such as `path`, `headers`, or `files`) gain
an `_arg` suffix; their wire names are preserved. `UploadFile` carries optional
per-part metadata without reading an open file eagerly:

Bytes and default `UploadFile` inputs use the filename `upload`; bare handles
use their basename when available. Set `UploadFile(filename=None, ...)`
explicitly to send a filename-less part.

```python
await client.upload_documents(
    documents=[
        UploadFile(open("a.pdf", "rb"), filename="a.pdf"),
        UploadFile(open("b.pdf", "rb"), filename="b.pdf"),
    ],
    category="contracts",
)
```

Multipart boundaries remain under the HTTP transport's control. This replaces
the old Pydantic multipart `body` argument; regenerate and update multipart
call sites to pass fields directly.

Successful binary responses also get a streaming context-manager variant. The
buffered method remains available for small responses:

For endpoints with mixed success representations, buffered methods return the
declared bytes/model/text/None union. Streaming variants yield `BinaryStream`
for binary content and the parsed value for JSON, text, or empty successes.

```python
content = await client.download_recording(recording_id)

async with client.stream_download_recording(recording_id) as recording:
    async for chunk in recording.iter_bytes(chunk_size=64 * 1024):
        await destination.write(chunk)

print(recording.media_type, recording.content_length, recording.filename)
```

The streaming context owns the individual response only. The generated wrapper
closes entered responses even when validation or reading is cancelled, and
treats its injected HTTP client as borrowed, so closing the wrapper does not
close a shared application transport:

```python
http_client = httpx.AsyncClient()
async with PaymentsClient(
    http_client,
    "https://payments.example.com/api",
    credentials={"bearerAuth": "your-token"},
) as client:
    ...

await http_client.aclose()
```

All operation failures derive from `ClientError`. `TransportError` retains its
original `cause`, including failures during binary iteration.
`ResponseValidationError` retains both the response and cause,
and `ApiError` exposes a parsed `detail` plus convenient `code` and `message`
properties. `body` and `parsed_body` remain compatibility aliases for
`raw_body` and `detail`.

### Generated models

`allOf` becomes inheritance, `oneOf` + `discriminator` becomes a Pydantic discriminated union, string enums become `StrEnum`, and `minimum` / `maxLength` survive as `Field(...)` constraints:

```python
class ChargeStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class Money(BaseModel):
    amount_cents: int
    currency: str = Field(min_length=3, max_length=3)


class CardPaymentMethod(BaseModel):
    type: Literal[PaymentMethodType.CARD]
    card_number: str
    exp_month: int = Field(ge=1, le=12)
    exp_year: int
    billing_address: Address | None = None


PaymentMethod = Annotated[
    CardPaymentMethod | BankTransferPaymentMethod,
    Field(discriminator="type"),
]


class BaseEntity(BaseModel):
    id: str
    created_at: datetime


class Charge(BaseEntity):          # allOf: BaseEntity + own properties
    amount: Money
    status: ChargeStatus
    payment_method: PaymentMethod  # discriminated at parse time
    metadata: dict[str, str] | None = None
```

Everything is re-exported from the package root, so consumers import from one place:

```python
from payments import ApiError, Charge, ChargeStatus, Money, PaymentsClient
```

## CLI reference

```
httpxgen OPENAPI OUTPUT [--package-name NAME] [--client-name NAME] [--http-client {protocol,httpx,httpx2}] [--tag TAG] [--schema-tag TAG] [--check]
```

| Argument | Meaning |
| --- | --- |
| `OPENAPI` | OpenAPI JSON or YAML file |
| `OUTPUT` | target package directory, or the root holding one package per tag when several `--tag` are given (created if missing) |
| `--package-name` | complete generated import package; defaults to the output directory name |
| `--client-name` | exact single-client class name; not available for multi-tag workspaces |
| `--http-client` | HTTP client annotation: `protocol` supports both implementations (default), or bind generated code directly to `httpx` or `httpx2` |
| `--tag TAG` | generate only operations carrying this tag; repeat it for one package per tag |
| `--schema-tag TAG` | keep schemas referenced by this tag without generating its operations; repeatable |
| `--check` | write nothing; exit non-zero when the checked-in output is stale |

Carve a focused client out of a large spec:

```sh
httpxgen openapi.json src/billing \
  --package-name billing \
  --tag charges \
  --schema-tag webhooks
```

For a single client, the default class name comes from the final package
segment: `generated.browser_worker` produces `BrowserWorkerClient`. Override it
verbatim when the API needs a different public identity:

```sh
httpxgen openapi.json src/generated/browser_worker \
  --package-name generated.browser_worker \
  --client-name ProvisionerClient \
  --http-client httpx2
```

Keep the default `protocol` when the same generated package should accept both
`httpx.AsyncClient` and `httpx2.AsyncClient` without a runtime dependency on
either implementation.

Repeat `--tag` and you get one client package per tag. The exception hierarchy,
transport types, `HttpMethods`, and serialization helpers are generated once in
`shared/`, and every model lands in
the package that uses it — `shared/models.py` holds only what more than one tag
references. Generated modules import each other absolutely, so the output reads
the same wherever you open it:

```sh
httpxgen specs/api.yml src/api --package-name api --tag payments --tag invoices
```

```python
# src/api/invoices/client.py
from api.invoices.models import CreateInvoiceRequest, Invoice, InvoicePage
from api.shared import AsyncHttpClient, ClientError, HttpMethods, serialize_path
from api.shared.models import ApiErrorModel
```

```python
from api import ClientError, InvoicesClient, Money, PaymentsClient
```

Every managed file starts with a `# Generated by httpxgen. DO NOT EDIT.` header. Files without it are never overwritten — httpxgen aborts instead.

## Automation and CI

Generated code is checked in, so a tiny script is usually all the automation you need.

`scripts/generate-client.sh`:

```sh
#!/usr/bin/env sh
set -eu

SPEC_URL="https://payments.example.com/api/openapi.json"
OUT="src/payments"

curl -fsSL "$SPEC_URL" -o openapi.json
uvx httpxgen openapi.json "$OUT" --package-name payments

echo "client regenerated in $OUT"
```

```sh
chmod +x scripts/generate-client.sh
./scripts/generate-client.sh
```

Use the `--check` variant in CI so a drifting spec fails the build instead of surprising you at runtime:

```yaml
# .github/workflows/client.yml
- name: Verify generated client is current
  run: |
    curl -fsSL "$SPEC_URL" -o openapi.json
    uvx httpxgen openapi.json src/payments --package-name payments --check
```

```
Generated HTTP client is current.
```

Or wire it into a `Makefile`:

```make
.PHONY: client client-check

client:
	uvx httpxgen openapi.json src/payments --package-name payments

client-check:
	uvx httpxgen openapi.json src/payments --package-name payments --check
```

## Supported scope

Exact `oneOf` membership uses JSON types without string/number/boolean coercion.
Formatted date/UUID strings remain valid, and mathematically integral JSON
numbers count as integers. Zero or multiple matching branches are rejected.

Query names beginning with `_` or `model_` receive a public `field`/`field_`
prefix in generated signatures and query models. Their wire names and
validation constraints remain intact.

Leading-underscore schema properties also receive a `field` prefix (for example,
`_id` becomes `field_id`) and keep an explicit wire alias. They are validated
ordinary model fields, including when additional properties are forbidden.

Operation names that collide with generated lifecycle methods or streaming
companions fail generation before writing files; rename the conflicting
`operationId` in the specification.

Local Path Item references are resolved before schema normalization and tag
selection. Authored siblings replace the corresponding inherited fields;
omitted siblings preserve inherited parameters and operations. Cycles fail
generation with a specific error.

References to nullable object components accept null in response bodies, request
arguments, and nested fields while keeping the object model's required fields
and constraints. OpenAPI 3.0 `nullable` requires an explicit type.

URL-encoded forms honor supported per-field style/explode encodings and JSON
contentType. Object values use JSON by default; explicit form styles can flatten
simple objects. Unsupported encoding options (including form allowReserved)
fail generation.

Multipart object fields and object-array items are JSON parts with aliases and
the declared `encoding.contentType` (JSON/+json), or application/json by default.
File parts also honor `encoding.contentType`. Unsupported multipart encoding
options fail generation explicitly.

Dot-valued path identifiers (`.` and `..`) are percent-encoded to preserve the
route boundary instead of allowing URL dot-segment normalization.

httpxgen targets ordinary OpenAPI 3.0 and 3.1 client specifications, not every
JSON Schema feature. It supports JSON/YAML input, local component references,
path/query/header/cookie serialization, JSON/form/multipart/binary request
bodies, JSON/text/binary responses, numeric/default/status-range responses,
typed error bodies, common
security schemes, directional request/response models, inline and recursive
Pydantic models, enums, nullable values, discriminated unions, and practical
`allOf` inheritance.

Unsupported constructs fail generation where possible. Important remaining
limitations are external references, callbacks/webhooks, automatic
pagination, and a synchronous client.

## Development

```sh
uv sync --all-groups
uv run pytest
uv run ruff check .          # lint
uv run ruff format .         # format
```

`preview/` is generated output, checked in so the effect of a change is visible
in review. Regenerate it whenever generated code changes — CI fails if it is
stale:

```sh
./scripts/generate-preview.sh
```

## License

MIT
