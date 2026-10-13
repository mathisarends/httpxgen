# 034: Keep ApiError.code and message useful when an error response declares headers

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

An error response with declared headers is wrapped in a generated result model whose body holds the actual error payload. ApiError.code/message look only at the wrapper itself, so both become None although the parsed body contains them. Adding response headers unexpectedly breaks convenience error handling.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 679 (_response_result)
- [httpxgen/generator/templates/exceptions.jinja2](../httpxgen/generator/templates/exceptions.jinja2), line 71 (_detail_value)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define a 400 JSON Error model with required string code/message and a response header X-Trace. Return {'code':'bad','message':'failed'} with X-Trace='abc'. ApiError.detail is a result wrapper containing body=Error(...), but error.code and error.message are both None.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Define a consistent error-detail/header representation and teach convenience accessors to reach the actual typed payload where appropriate.
- Preserve parsed_body/body compatibility aliases and access to response headers.
- Avoid ambiguous unwrapping of arbitrary user payloads merely because they have a property named body.

## Acceptance criteria

- [ ] The reproduced ApiError exposes code='bad' and message='failed'.
- [ ] Response-header data and typed error-body data remain accessible.
- [ ] Errors without headers and dictionary-shaped details retain their behavior.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py tests/generator/test_improvements.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
