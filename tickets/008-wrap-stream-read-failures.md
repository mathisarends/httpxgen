# 008: Translate binary stream read failures into the generated client error hierarchy

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Transport exception translation currently covers entering the HTTP stream, but not reading it. Both buffered binary methods and BinaryStream.iter_bytes leak raw HTTPX read exceptions, violating the documented ability to catch operation failures as ClientError.

## Relevant code

- [httpxgen/generator/templates/transport.jinja2](../httpxgen/generator/templates/transport.jinja2), line 82 (BinaryStream.iter_bytes)
- [httpxgen/generator/templates/binary_operation.jinja2](../httpxgen/generator/templates/binary_operation.jinja2), line 6 (buffered download)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Create an httpx.AsyncByteStream that yields b'ab' and then raises httpx.ReadError('connection lost mid-download'). Return it as a 200 application/octet-stream response. Both await client.run() and async iteration inside client.stream_run() raise raw ReadError; isinstance(error, generated.ClientError) is false.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Wrap transport failures originating from response iteration while preserving the original exception in cause and __cause__.
- Avoid wrapping exceptions raised by consumer code inside the streaming context.
- Keep cancellation unchanged and ensure response cleanup still runs.

## Acceptance criteria

- [ ] Mid-download read failures in buffered and streaming calls raise TransportError derived from ClientError.
- [ ] The original transport exception is preserved.
- [ ] Consumer exceptions and cancellation are not mislabeled as transport failures.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_improvements.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
