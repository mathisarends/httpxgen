# httpxgen

Generate a **typed async [httpx](https://www.python-httpx.org/) client** from an OpenAPI document — no runtime layer, no reflection, no magic.

httpxgen emits plain Python you could have written by hand: `async def` methods with real parameter names, [Pydantic](https://docs.pydantic.dev/) models for every schema, discriminated unions for `oneOf`, `StrEnum` for enums, and `UUID` / `datetime` where the spec says so. Check the output into your repo, read it, click through it in your editor.

```
openapi.json  ──▶  httpxgen  ──▶  payments/
                                    ├── __init__.py
                                    ├── client.py
                                    ├── models.py
                                    ├── exceptions.py
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
httpxgen openapi.json src/payments --package-name payments
```

```
Generated 5 file(s) in package src/payments.
```

```python
import asyncio

from payments import ApiError, CardPaymentMethod, CreateChargeRequest, Money, PaymentsClient


async def main() -> None:
    async with PaymentsClient(
        "https://payments.example.com/api",
        headers={"Authorization": "Bearer …"},
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

```python
class PaymentsClient:
    async def list_charges(
        self,
        status: ChargeStatus | None = None,
        cursor: str | None = None,
        page_size: int | None = None,
        *,
        timeout: float | None = None,
    ) -> ChargePage:
        path = "/charges"
        params: dict[str, Any] = {}
        if status is not None:
            params["status"] = status
        if cursor is not None:
            params["cursor"] = cursor
        if page_size is not None:
            params["page_size"] = page_size

        response = await self._client.request(
            "GET",
            f"{self._base_url}{path}",
            params=params,
            headers=self._headers,
            timeout=self._timeout if timeout is None else timeout,
        )

        if response.status_code == 200:
            return ChargePage.model_validate(response.json())

        raise ApiError(response.status_code, response.text)
```

Path parameters carry their spec format — `format: uuid` becomes `UUID`, not `str`:

```python
    async def get_customer(
        self,
        customer_id: UUID,
        *,
        timeout: float | None = None,
    ) -> Customer:
        path = f"/customers/{customer_id}"
        ...
```

Request bodies are a single typed `body` argument, serialized by alias and without `None` noise:

```python
    async def create_charge(
        self,
        body: CreateChargeRequest,
        *,
        timeout: float | None = None,
    ) -> Charge:
        path = "/charges"

        json_body = (
            TypeAdapter(CreateChargeRequest).dump_python(
                body, mode="json", by_alias=True, exclude_none=True
            )
            if body is not None
            else None
        )
        ...
```

The client is an async context manager, so `httpx` connections are closed for you:

```python
async with PaymentsClient("https://payments.example.com/api") as client:
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
| `OPENAPI` | OpenAPI **JSON** file |
| `OUTPUT` | exact target package directory (created if missing) |
| `--package-name` | import name and client class prefix; defaults to the output directory name |
| `--tag TAG` | generate only operations carrying this tag; repeatable |
| `--schema-tag TAG` | keep schemas referenced by this tag without generating its operations; repeatable |
| `--check` | write nothing; exit non-zero when the checked-in output is stale |

Carve a focused client out of a large spec:

```sh
httpxgen openapi.json src/billing \
  --package-name billing \
  --tag charges --tag refunds \
  --schema-tag webhooks
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

httpxgen deliberately targets a small, sharp happy path rather than every corner of the OpenAPI surface.

**Supported** — OpenAPI 3.x, operations with a unique `operationId`, path/query/header parameters, `application/json` request bodies, explicit numeric 2xx responses, Pydantic models, string enums, local `$ref`s, `allOf` inheritance, `oneOf` / `anyOf` unions with discriminators, `date` / `date-time` / `uuid` formats, and one async client.

**Not supported yet** — authentication schemes, non-JSON content (multipart, form, binary, streaming), typed error bodies, `default` and `2XX` response ranges, cookie parameters, parameter `style` / `explode` serialization, external `$ref`s, and sync clients.

See [`MISSING_IMPL.md`](MISSING_IMPL.md) for the full gap analysis.

## Development

```sh
uv sync
uv run pytest
```

## License

MIT
