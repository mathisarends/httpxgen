# 027: Reject unsupported request content_type choices instead of sending an empty body

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

The generated multi-media body dispatcher has if/elif branches without an else. Literal annotations do not enforce runtime values, so an unsupported content_type silently leaves body_arguments empty and sends a bodyless request, even when the body is required.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 486 (_render_body)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 269 (content_type argument)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate a required body offering application/json and text/plain. Call run('hello', content_type='application/xml') from a runtime/dynamic caller. The captured request content is b'' and no validation error is raised.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Add an explicit runtime failure path listing the declared choices.
- Raise RequestValidationError at the existing preparation boundary and avoid making a network call.
- Keep required/optional behavior and selected-media serialization consistent.

## Acceptance criteria

- [ ] An unsupported media choice fails before sending any request.
- [ ] Every declared media choice continues to serialize correctly.
- [ ] The exception identifies the supplied choice and valid alternatives.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py tests/generator/test_client.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
