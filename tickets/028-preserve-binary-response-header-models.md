# 028: Validate and expose declared response headers for binary success responses

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Ordinary responses use generated result models for declared headers, but the binary template returns bytes and never uses that result model or its header validation. Declared header contracts disappear as soon as the success body is binary.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 327 (_render_stream_response_handling)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 679 (_response_result)
- httpxgen/generator/templates/binary_operation.jinja2

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate a 200 application/octet-stream response with header X-Count={schema:{type:integer}}. Return b'ab' with X-Count='not-an-int'. The buffered method returns b'ab' successfully instead of ResponseValidationError, and no typed result exposes X-Count.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Design consistent buffered and streaming representations for binary responses with declared headers.
- Share header extraction/validation with ordinary response handling rather than duplicating an incompatible path.
- Keep incremental streaming and convenient byte-only behavior for endpoints without declared header result models.

## Acceptance criteria

- [ ] Malformed declared binary-response headers raise ResponseValidationError.
- [ ] Valid declared headers are accessible through a documented typed result/stream interface.
- [ ] Binary methods without declared headers retain their working behavior.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py tests/generator/test_improvements.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
