# httpxgen

Generate a **typed async [httpx](https://www.python-httpx.org/) client** from an OpenAPI document — no runtime layer, no reflection, no magic.

httpxgen emits plain Python you could have written by hand: `async def` methods with real parameter names, [Pydantic](https://docs.pydantic.dev/) models for every schema, discriminated unions for `oneOf`, `StrEnum` for enums, and `UUID` / `datetime` where the spec says so. Check the output into your repo, read it, click through it in your editor.

```
openapi.json  ──▶  httpxgen  ──▶  payments/
                                    ├── __init__.py
                                    ├── client.py         # the public client class
                                    ├── models.py
                                    ├── exceptions.py     # ApiError
                                    ├── serialization.py  # parameter and auth helpers
                                    └── py.typed
```

Split a large document along its tags and the support modules are generated once,
beside the clients that share them:

```
openapi.json  ──▶  httpxgen  ──▶  api/
                                    ├── __init__.py       # clients, ApiError, all models
                                    ├── shared/           # generated once
                                    │     ├── exceptions.py
                                    │     ├── models.py   # only models used by both tags
                                    │     └── serialization.py
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

httpxgen is only needed at build time — the generated package depends on `httpx` and `pydantic` alone.

## Quick start

```sh
httpxgen openapi.yaml src/payments --package-name payments
```

```
Generated 6 file(s) in package src/payments.
```

```python
import asyncio

import httpx

from payments import ApiError, CardPaymentMethod, CreateChargeRequest, Money, PaymentsClient


async def main() -> None:
    async with PaymentsClient(
        httpx.AsyncClient(),
        "https://payments.example.com/api",
        credentials={"bearerAuth": "your-token"},
    ) as client:
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
        except ApiError as error:
            print(error.status_code, error.body)
            if error.parsed_body is not None:
                print(error.parsed_body)


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

        response = await self._client.request(
            method="GET",
            url=f"{self._base_url}{path}",
            params=query,
            headers=headers,
            timeout=self._timeout if timeout is None else timeout,
        )

        if response.status_code == 200:
            return ChargePage.model_validate(response.json())

        raise ApiError(response.status_code, response.text, response=response)
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
            method="GET",
            url=f"{self._base_url}{path}",
            headers=headers,
            timeout=self._timeout if timeout is None else timeout,
        )

        if response.status_code == 200:
            return Customer.model_validate(response.json())
        if response.status_code == 404:
            parsed_body = ApiErrorModel.model_validate(response.json())
            raise ApiError(response.status_code, response.text, parsed_body, response)

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

The same direct shape is used for other ordinary body encodings:
`application/x-www-form-urlencoded` is passed as `data=`, multipart object
fields are separated into `data=` and `files=`, and binary payloads use
`content=`. Multipart boundaries remain under `httpx`'s control.

The client is an async context manager, so `httpx` connections are closed for you:

```python
http_client = httpx.AsyncClient()
async with PaymentsClient(
    http_client,
    "https://payments.example.com/api",
    credentials={"bearerAuth": "your-token"},
) as client:
    ...
```

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
httpxgen OPENAPI OUTPUT [--package-name NAME] [--tag TAG] [--schema-tag TAG] [--check]
```

| Argument | Meaning |
| --- | --- |
| `OPENAPI` | OpenAPI JSON or YAML file |
| `OUTPUT` | target package directory, or the root holding one package per tag when several `--tag` are given (created if missing) |
| `--package-name` | import name and client class prefix; defaults to the output directory name |
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

Repeat `--tag` and you get one client package per tag. `ApiError` and the
serialization helpers are generated once in `shared/`, and every model lands in
the package that uses it — `shared/models.py` holds only what more than one tag
references. Generated modules import each other absolutely, so the output reads
the same wherever you open it:

```sh
httpxgen specs/api.yml src/api --package-name api --tag payments --tag invoices
```

```python
# src/api/invoices/client.py
from api.invoices.models import CreateInvoiceRequest, Invoice, InvoicePage
from api.shared import ApiError, apply_security, serialize_path
from api.shared.models import ApiErrorModel
```

```python
from api import ApiError, InvoicesClient, Money, PaymentsClient
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

## How the Payments API is handled

The repository fixture in `specs/api.yml` is the executable reference for a
normal, non-trivial API:

- Its global `bearerAuth` requirement becomes the `credentials` entry shown
  above. `getCustomer` declares `security: []`, so that method remains public.
- `page_size` is validated to be between 1 and 200 and defaults to 25. Optional
  query values are omitted; arrays and objects follow their OpenAPI
  `style`/`explode` rules.
- Path values are percent-encoded. A value containing `/` remains one path
  segment instead of changing the endpoint.
- `CreateChargeRequest` is serialized as JSON by alias. JSON-compatible vendor
  media types such as `application/problem+json` are handled as JSON too.
- A successful charge response becomes `Charge`. The documented 402 response
  raises `ApiError`; its validated `ChargeError` is available as
  `error.parsed_body`. Undocumented statuses also raise `ApiError`, with the
  original `httpx.Response` on `error.response`.
- The nested billing profile becomes a real generated model rather than
  `dict[str, Any]`. Unknown response fields are retained unless the schema says
  `additionalProperties: false`.
- Schemas containing `readOnly` or `writeOnly` properties are split where they
  cross the HTTP boundary. For example, a shared `User` schema becomes
  `UserRequest` without read-only fields and `UserResponse` without write-only
  fields, so neither side requires data it cannot provide.
- `oneOf` plus `discriminator` becomes a discriminated Pydantic union. Recursive
  object models and discriminator `mapping` values are supported.
- The schema component named `ApiError` is generated as `ApiErrorModel` to avoid
  colliding with the runtime exception.

When an operation offers several content types, httpxgen prefers JSON (including
`+json`) and otherwise uses the first supported text or binary response type.
Request bodies must be JSON. Pass the base URL explicitly: `servers` is not used
as an implicit network destination.

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
limitations are exact non-discriminated `oneOf` semantics, multiple selectable
media types, response-header return models, external references, streaming,
callbacks/webhooks, automatic pagination, and a synchronous client.

See [`MISSING_IMPL.md`](MISSING_IMPL.md) for the prioritized checklist and the
test requirements for each future step.

## Development

```sh
uv sync
uv run pytest
```

## License

MIT
