# Cleaner generated client APIs

## Context

The generated client is currently too closely coupled to `httpx` internals and
does not provide enough application-level abstractions for errors and large
binary transfers. The concrete integration in `browser-provisioner` exposes
three recurring problems:

1. The generated client requires an `httpx.AsyncClient`, while the application
   uses an API-compatible `httpx2.AsyncClient`. Consumers therefore need
   `cast(Any, ...)` at every construction site.
2. Only non-success HTTP responses are represented as `ApiError`. Transport
   failures and response validation failures escape as unrelated `HTTPError`,
   `ValidationError`, or `ValueError` instances. Consumers must repeat broad
   exception tuples around almost every generated operation.
3. Binary responses are always materialized through `response.content`. Large
   recordings and downloads cannot be transferred incrementally, so consumers
   bypass the generated operation and rebuild its URL, timeout, status handling,
   and streaming behavior manually.

The multipart implementation has related limitations:

- It recognizes only properties whose own schema has `format: binary`.
  Standard multi-file fields expressed as `array` with binary `items` are not
  recognized as files.
- It builds `files` as `dict[str, bytes]`. A dictionary cannot represent
  repeated multipart field names and the `bytes` restriction requires the
  complete file to be resident in memory.
- Multipart bodies are passed through a Pydantic model and `model_dump()`.
  This representation is appropriate for structured data but not for open file
  handles or streaming content.
- Existing coverage exercises only one small in-memory `bytes` upload, so it
  does not validate multi-file encoding or memory-safe file inputs.

## Goals

- Generated clients accept compatible asynchronous HTTP transports without
  casts in consumer code.
- Consumers can catch one generated base exception for all failures originating
  from a client operation.
- Documented API errors retain their parsed, typed error model.
- Binary responses can be processed incrementally without duplicating generated
  request and error logic.
- Binary and multipart requests can use file-like or streaming inputs rather
  than requiring complete in-memory `bytes` values.
- Multipart arrays are encoded as repeated parts with the correct wire name.
- Ordinary JSON, form, text, and small binary operations remain simple.
- Generated client class names describe the API rather than its installation
  path or the fact that its source was generated.

## Non-goals

- Implementing a generic runtime framework behind generated clients.
- Adding automatic retries, pagination, or resumable upload protocols.
- Hiding the generated request construction or OpenAPI response branches.
- Requiring one concrete HTTP implementation such as `httpx` or `httpx2`.

## 1. Client naming and package identity

Package location and public client identity are separate concepts and must not
be derived from the same unprocessed value.

The current single-client implementation constructs the class name from the
complete `package_name`:

```python
client_name = f"{class_name(package_name)}Client"
```

In `browser-provisioner`, the import package is `generated.browser_worker`.
Normalizing that full dotted path therefore produces the unnecessarily verbose
class name `GeneratedBrowserWorkerClient`. The `Generated` prefix is an
installation detail, not part of the API domain. A similar package path such as
`generated.backend_worker` would incorrectly produce
`GeneratedBackendWorkerClient`.

This is a generator design defect rather than an OpenAPI modeling error. The
consumer should not have to rename its package or add a handwritten alias to get
a clean public API.

### Required naming precedence

For a single generated client, resolve its name in this order:

1. An explicit `client_name` option supplied through the Python API or
   `--client-name` through the CLI.
2. Otherwise, the final segment of `package_name`, not the complete import path.
3. If `package_name` was omitted, the final segment of the output directory as
   it is today.

Examples:

| Package/import path | Explicit name | Generated class |
| --- | --- | --- |
| `generated.browser_worker` | omitted | `BrowserWorkerClient` |
| `company.payments` | omitted | `PaymentsClient` |
| `generated.api` | `ProvisionerClient` | `ProvisionerClient` |
| `ordinary_api` | omitted | `OrdinaryApiClient` |

The generator must not heuristically strip words such as `api`, `backend`,
`service`, or `worker`: they may be meaningful domain terms. Callers can remove
or replace them explicitly with `--client-name`. Only module-path prefixes are
discarded by the default rule.

The explicit name is the complete class name and is used verbatim after
validation. The generator must not append a `Client` suffix automatically.
Invalid Python identifiers, keyword names, and collisions with generated models
or support types must fail generation with an actionable error.

For workspaces split by multiple tags, the existing tag-derived client names
remain the appropriate default because each tag identifies a distinct API
surface. A single global `--client-name` must either be rejected for multi-tag
generation or replaced later by a separately designed per-tag naming option; it
must not silently rename only one generated client.

With this change, the intended `browser-provisioner` usage becomes:

```python
from generated.browser_worker import BrowserWorkerClient

client = BrowserWorkerClient(http, browser_worker_url)
```

There should be no `Generated` prefix in a public class merely because the
package lives below a `generated` namespace.

## 2. Transport abstraction

Replace the concrete constructor annotation with a generated structural
protocol containing only the operations the client actually needs. At minimum,
the protocol must cover `request()`, `stream()`, and `aclose()` where applicable.

Conceptually:

```python
class AsyncHttpClient(Protocol):
    async def request(self, method: str, url: str, **kwargs: Any) -> HttpResponse: ...

    def stream(
        self, method: str, url: str, **kwargs: Any
    ) -> AsyncContextManager[HttpResponse]: ...

    async def aclose(self) -> None: ...
```

The response should likewise be described structurally using only the members
needed by generated code, such as `status_code`, `headers`, `text`, `content`,
`json()`, and `aiter_bytes()`.

The generated constructor then accepts `AsyncHttpClient` rather than
`httpx.AsyncClient`:

```python
client = BrowserWorkerClient(
    http_client,
    browser_worker_url,
    timeout=30.0,
)
```

Both `httpx.AsyncClient` and `httpx2.AsyncClient` must satisfy the protocol
without `Any` casts or adapters.

### Transport ownership

The lifecycle contract must be explicit. Because the transport is injected by
the caller, it should be treated as borrowed by default. Closing a short-lived
generated wrapper must not unexpectedly close a shared application transport.
If owned transports are supported later, ownership should be an explicit
constructor option or separate factory.

## 3. Unified client errors

Generate a common exception hierarchy:

```python
class ClientError(Exception):
    """Base class for failures produced by a generated client operation."""


class TransportError(ClientError):
    cause: Exception


class ResponseValidationError(ClientError):
    status_code: int
    response: HttpResponse
    cause: Exception


class ApiError(ClientError):
    status_code: int
    detail: object | None
    response: HttpResponse
```

The generated operation must translate failures at its boundary:

- Exceptions raised while executing the HTTP request become `TransportError`.
- Malformed JSON, incompatible response bodies, and invalid response headers
  become `ResponseValidationError`.
- Documented non-success responses and unexpected status codes remain
  `ApiError`.
- Existing `ClientError` instances must be re-raised unchanged.
- Cancellation and other `BaseException` subclasses must not be wrapped.

This allows ordinary consumer code to catch one type:

```python
try:
    state = await client.capture_browser_state()
except ClientError as error:
    raise BrowserStateTransferException("Could not capture state") from error
```

Specific documented failures remain distinguishable through their parsed model:

```python
try:
    return await client.download_file(download_id)
except ApiError as error:
    if isinstance(error.detail, DownloadNotFoundError):
        raise DownloadNotFoundException() from error
    raise
```

`ApiError` should expose convenience properties such as `code` and `message`
when its parsed detail contains those fields. Consumer code should not need
`getattr(error.parsed_body, "code", None)`.

For compatibility, the current `parsed_body` and raw `body` attributes may be
kept as deprecated aliases during a transition. New generated examples and
documentation should use `detail` and an explicitly named `raw_body` property.

## 4. Streaming binary responses

For every operation with a successful binary response, generate both:

- the existing convenient method returning `bytes`; and
- a streaming context-manager variant.

Example surface:

```python
content = await client.download_recording(recording_id)

async with client.stream_download_recording(recording_id) as file:
    await storage.put(
        StoredObject(
            content=file.iter_bytes(chunk_size=64 * 1024),
            content_type=file.media_type,
        )
    )
```

The yielded object should provide at least:

```python
class BinaryStream:
    media_type: str | None
    content_length: int | None
    filename: str | None
    headers: Mapping[str, str]

    def iter_bytes(self, chunk_size: int | None = None) -> AsyncIterator[bytes]: ...
```

The stream context manager owns only the individual response lifecycle. Leaving
the context must close the response, not the injected shared HTTP client.

Status matching, content-type validation, parsing of error responses, and
exception translation must be shared between the buffered and streaming paths.
The buffered convenience method should be implemented on top of the streaming
path where practical, so the protocol logic cannot drift between the two.

For a success response offering multiple binary media types, `media_type` must
report the normalized actual response content type. An unsupported content type
must produce `ResponseValidationError`, not an untyped `ValueError`.

## 5. Large binary request bodies

An `application/octet-stream` request must not be limited to `bytes`. Its
generated input type should support incremental request bodies:

```python
BinaryContent = bytes | Iterable[bytes] | AsyncIterable[bytes]
```

The body must be passed directly as request content without Pydantic
serialization or eager concatenation.

## 6. Multipart and multi-file requests

### File-part abstraction

Generate or export a small transport-neutral file-part type:

```python
@dataclass(frozen=True)
class UploadFile:
    content: bytes | BinaryIO
    filename: str | None = None
    content_type: str | None = None
    headers: Mapping[str, str] | None = None
```

The generator converts this type to the tuple representation expected by the
selected HTTP transport. A plain `bytes` or binary file handle may be accepted
as shorthand where no metadata is needed.

Multipart file handles must never be read eagerly by generated serialization
code.

### Generated method shape

Multipart fields should be represented directly in the operation signature
rather than being hidden inside a Pydantic body model that requires `bytes`.
For example, this OpenAPI shape:

```yaml
type: object
required: [documents, category]
properties:
  documents:
    type: array
    items:
      type: string
      format: binary
  category:
    type: string
```

should produce an API resembling:

```python
await client.upload_documents(
    documents=[
        UploadFile(open("a.pdf", "rb"), filename="a.pdf"),
        UploadFile(open("b.pdf", "rb"), filename="b.pdf"),
    ],
    category="contracts",
)
```

Required multipart fields must remain required parameters. Optional fields must
use `None` and be omitted from the encoded request when absent.

If flattening fields would collide with path, query, header, or generated
control parameters such as `timeout`, generation must fail with a useful error
or apply a deterministic, documented name disambiguation rule.

### Multipart encoding

The generated code must use a sequence of pairs rather than a dictionary:

```python
files: list[tuple[str, FilePart]] = []
files.extend(("documents", document) for document in documents)
```

This preserves repeated wire names required by multi-file fields. Scalar form
data should likewise preserve repeated values where the OpenAPI schema permits
arrays.

Multipart boundaries remain the responsibility of the HTTP transport. Generated
code must not set a bare `Content-Type: multipart/form-data` header because doing
so would omit the transport-generated boundary.

## 7. Expected browser-provisioner result

After regeneration, `browser-provisioner` should no longer need:

- the verbose `GeneratedBrowserWorkerClient` name;
- `cast(Any, self._http)` when constructing generated clients;
- repeated `(ApiError, HTTPError, ValidationError, ValueError)` exception tuples;
- `getattr(error.parsed_body, "code", None)`;
- hand-built URLs and direct `_http.stream()` calls for generated binary
  endpoints; or
- duplicated status and content-type handling around recording downloads.

The application integration should reduce to domain translation around the
generated client:

```python
try:
    client = self._client(browser)
    state = await client.capture_browser_state()
except ClientError as error:
    raise _as_transfer_failure("read browser state from", error) from error
```

and:

```python
client = self._client(browser, transfer=True)
async with client.stream_download_recording(recording_id) as recording:
    await self._storage.put(
        StoredObject(
            key=key,
            content=recording.iter_bytes(chunk_size=64 * 1024),
            content_type=recording.media_type or "application/octet-stream",
        )
    )
```

## 8. Tests and acceptance criteria

### Naming

- `package_name="generated.browser_worker"` generates
  `BrowserWorkerClient` by default.
- `package_name="company.payments"` generates `PaymentsClient` by default.
- `client_name="ProvisionerClient"` overrides the inferred name exactly.
- An explicit name without a `Client` suffix is accepted verbatim; explicit
  values are never rewritten beyond validation.
- Invalid and colliding explicit names fail before files are written.
- Supplying a single client name during multi-tag generation fails with a clear
  explanation.
- Package imports continue to use the complete dotted `package_name`; changing
  class-name inference must not alter module paths.

### Transport and errors

- An `httpx.AsyncClient` satisfies the generated transport protocol.
- An `httpx2.AsyncClient` satisfies the same protocol without a cast.
- Request failures are raised as `TransportError` with the original exception as
  `__cause__`.
- Invalid JSON, invalid typed bodies, invalid response headers, and unsupported
  response content types are raised as `ResponseValidationError`.
- Documented non-success responses produce `ApiError` containing the parsed
  typed detail.
- Unexpected status codes produce `ApiError` with `detail is None` and preserve
  the response.
- All generated operation failures can be caught as `ClientError`.

### Streaming downloads

- A binary response can be consumed chunk by chunk without accessing
  `response.content`.
- The response remains open while inside the stream context and closes on exit,
  including exceptional exits.
- Error responses received by a streaming operation are parsed through the same
  error path as buffered operations.
- The buffered binary method still returns `bytes` and uses the same response
  validation rules.
- Multiple declared binary media types report the actual normalized media type.

### Multipart uploads

- A single `bytes` file remains supported.
- An open binary file can be uploaded without being read eagerly by generated
  code.
- An array of binary files is encoded as repeated parts with the same wire name.
- Optional file fields are omitted when `None`.
- Filenames, per-part content types, and per-part headers are preserved.
- Multipart boundaries are generated by the HTTP transport.
- A test uses a file-like object that fails if the generator attempts an eager
  full read, preventing regressions to in-memory buffering.

## 9. Implementation order

1. Separate `client_name` from `package_name`, add the CLI/Python override, and
   switch default inference to the final package segment.
2. Introduce the transport and response protocols and remove the concrete
   `httpx.AsyncClient` annotation.
3. Add `ClientError`, `TransportError`, and `ResponseValidationError`; update
   generated request and parsing boundaries.
4. Generate streaming variants for successful binary responses and implement
   buffered binary methods through the shared response path.
5. Extend request-body analysis to distinguish single binary fields from arrays
   of binary fields.
6. Introduce `UploadFile`, flatten multipart operation parameters, and encode
   files as repeated pairs.
7. Regenerate the `browser-provisioner` client as `BrowserWorkerClient` and
   remove its casts, broad exception tuples, and manual recording download
   transport code.
8. Update the README and remove streaming from the list of general limitations.

The first three steps address the concrete readability and large-recording
problems in `browser-provisioner`. Multipart changes should follow as a separate,
focused change because they alter generated method signatures and therefore
need an explicit migration note.
