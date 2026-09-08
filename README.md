# httpxgen

Generate a **typed async [httpx](https://www.python-httpx.org/) client** from an OpenAPI document — no runtime layer, no reflection, no magic.

httpxgen emits plain Python you could have written by hand: `async def` methods with real parameter names, [Pydantic](https://docs.pydantic.dev/) models for every schema, discriminated unions for `oneOf`, `StrEnum` for enums, and `UUID` / `datetime` where the spec says so. Check the output into your repo, read it, click through it in your editor.

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

Split a large document along its tags and the support modules are generated once,
beside the clients that share them:

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

httpxgen is only needed at build time. Generated clients use `pydantic` for
models and accept any asynchronous HTTP client satisfying their structural
transport protocol, including `httpx.AsyncClient` and API-compatible clients.

## Quick start

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

## What the generated code looks like

### From this spec

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

### You get this client

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

Request bodies are a single typed `body` argument, serialized by alias and without `None` noise:

```python
    async def create_charge(
        self,
        body: CreateChargeRequest,
        *,
        timeout: float | None = None,
    ) -> Charge:
        ...
        json_body = TypeAdapter(CreateChargeRequest).dump_python(
            body, mode="json", by_alias=True, exclude_none=True
        )
        ...
```

The same direct shape is used for JSON, form, text, and small binary bodies.
An `application/octet-stream` body accepts `bytes`, `Iterable[bytes]`, or
`AsyncIterable[bytes]` and is passed directly as `content=`.

Multipart fields are flattened into method arguments. Binary arrays become
repeated parts with the same wire name, while `UploadFile` carries optional
per-part metadata without reading an open file eagerly:

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

```python
content = await client.download_recording(recording_id)

async with client.stream_download_recording(recording_id) as recording:
    async for chunk in recording.iter_bytes(chunk_size=64 * 1024):
        await destination.write(chunk)

print(recording.media_type, recording.content_length, recording.filename)
```

The streaming context owns the individual response only. The generated wrapper
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
original `cause`, `ResponseValidationError` retains both the response and cause,
and `ApiError` exposes a parsed `detail` plus convenient `code` and `message`
properties. `body` and `parsed_body` remain compatibility aliases for
`raw_body` and `detail`.

### And these models

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

## CLI

```
httpxgen OPENAPI OUTPUT [--package-name NAME] [--client-name NAME] [--tag TAG] [--schema-tag TAG] [--check]
```

| Argument | Meaning |
| --- | --- |
| `OPENAPI` | OpenAPI JSON or YAML file |
| `OUTPUT` | target package directory, or the root holding one package per tag when several `--tag` are given (created if missing) |
| `--package-name` | complete generated import package; defaults to the output directory name |
| `--client-name` | exact single-client class name; not available for multi-tag workspaces |
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
  --client-name ProvisionerClient
```

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

## Use it from a shell script

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

## Scope

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
