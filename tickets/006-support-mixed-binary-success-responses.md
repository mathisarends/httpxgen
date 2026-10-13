# 006: Preserve all documented success branches when an operation supports binary responses

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

The presence of any binary success response selects the binary operation template for the entire operation. That template returns bytes and only processes binary success branches. Other declared successful JSON/text/empty responses are rejected or misclassified as API errors.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 319 (_has_binary_success)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 327 (_render_stream_response_handling)
- httpxgen/generator/templates/binary_operation.jinja2

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Case A: one 200 response declares application/json and application/octet-stream. A valid application/json response is raised as ResponseValidationError for an unsupported Content-Type. Case B: the operation declares 200 binary and 204 empty; a valid 204 is raised as ApiError. A separate exact JSON status plus a binary 2XX range also needs correct precedence.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Keep the ordinary buffered method's full declared return union and status/media-type dispatch.
- Specify useful behavior for the streaming variant when a valid success is nonbinary, without incorrectly labeling that success as an API failure.
- Preserve exact-status precedence over ranges and shared error parsing.

## Acceptance criteria

- [ ] The buffered method accepts and returns every documented success representation.
- [ ] A documented 204 success is handled correctly.
- [ ] Binary streaming remains incremental and does not buffer a successful download merely to inspect it.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_improvements.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
