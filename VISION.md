# Vision

`httpxgen` turns a local OpenAPI document into a typed, asynchronous Python
client through an offline CLI. The result should be as pleasant to read and as
easy to understand as a handwritten client. Covering the API is not enough:
the generated source code itself is the product.

The output is ordinary Python with idiomatic names, signatures, and types,
clear module boundaries, and direct `httpx` calls. It can be checked into a
repository, explored in an editor, reviewed, and debugged like any other code.
Generation is local and deterministic; at runtime there is no reflection, no
dependency on `httpxgen`, and no hidden abstraction layer.

## Principles

- **Python first.** OpenAPI describes the contract, but does not dictate the
  shape of the public Python API. When trade-offs arise, favor an interface
  that is understandable, typed, and predictable for Python users.
- **Correctness over completeness.** We reliably support the constructs found
  in ordinary OpenAPI 3.0 and 3.1 specifications. Anything that cannot be
  translated unambiguously and correctly should fail early with a useful
  message instead of silently producing incorrect or loosely typed `Any` code.
- **Explicit over magical.** The base URL, credentials, and
  `httpx.AsyncClient` are supplied by the caller. Request construction,
  serialization, validation, and error handling remain visible in the
  generated code.
- **Keep simple things simple.** An ordinary operation should look like an
  ordinary method. Additional OpenAPI cases must not hide the common case
  behind generic dispatchers or a runtime framework.
- **Focused and composable.** Large specifications can be divided by tag into
  understandable clients with shared models, without losing sight of the
  complete contract.
- **Minimal runtime policy.** Retries, backoff, token lifecycle, and similar
  transport decisions belong in the injected `httpx` client or application
  code, not in the generator.

## Deliberate boundaries

`httpxgen` does not aim to implement every detail of OpenAPI or JSON Schema.
Rare constructs, external workflows, and features such as automatic
pagination, OAuth flows, streaming, or a second synchronous client are not
goals in themselves. They belong in the core only when they can be represented
faithfully without compromising the readability of the generated Python API.

An extension fits this vision when it expresses a common API more accurately
without making the generated code unnecessarily indirect. Otherwise, a clear
limitation is better than pretend support.
