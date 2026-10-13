# 007: Close entered HTTP responses when streaming setup or validation is cancelled

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

The response is entered before validation, but the unconditional finally block is only established around yield. asyncio.CancelledError bypasses the earlier Exception handlers. Cancellation while reading a streamed error body leaves the response and its underlying stream open instead of performing deterministic cleanup.

## Relevant code

- [httpxgen/generator/templates/binary_operation.jinja2](../httpxgen/generator/templates/binary_operation.jinja2), line 23 (response_stack)
- [httpxgen/generator/templates/binary_operation.jinja2](../httpxgen/generator/templates/binary_operation.jinja2), line 36 (response validation)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Use a custom httpx.AsyncByteStream for a 500 response. Its iterator sets an event and then waits indefinitely. Start the generated buffered download (which calls stream_run), wait for the event from response.aread(), cancel the task, and await cancellation. response.is_closed and the stream's close flag both remain false, including after another event-loop turn.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Put the entire lifetime after successfully entering a response under unconditional async context-manager/finally cleanup.
- Re-raise cancellation unchanged; cleanup must not require wrapping BaseException as ClientError.
- Handle validation errors and setup failures without double closing or closing the borrowed HTTP client.

## Acceptance criteria

- [ ] Cancellation during error-body reading closes the response promptly.
- [ ] Cancellation before and after yield preserves asyncio cancellation semantics.
- [ ] Normal and exceptional exits close the individual response once and keep the injected transport open.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_improvements.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
