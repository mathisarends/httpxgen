# 005: Prevent dot-valued path parameters from changing the target route

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

urllib.parse.quote leaves unreserved dots unchanged even with safe=''. When a path parameter is '.' or '..', HTTPX normalizes the resulting dot segment and requests a different route. For state-changing endpoints this can target an unintended resource.

## Relevant code

- [httpxgen/generator/templates/serialization.jinja2](../httpxgen/generator/templates/serialization.jinja2), line 65 (serialize_path)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 390 (_render_path)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate /items/{id}/delete with a required string path parameter. Call the operation with id='..'. The observed HTTPX URL is https://example.test/delete rather than a route containing an encoded item identifier. Exercise '.' and both trailing and interior placeholder positions as well.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Protect path-parameter boundaries against dot-segment normalization, or reject values that cannot be represented faithfully with an actionable RequestValidationError.
- Verify the actual URL emitted by HTTPX, not only the helper's return string.
- Preserve correct escaping of slashes, percent signs, and ordinary identifiers.

## Acceptance criteria

- [ ] A dot-valued identifier never redirects the request to another route.
- [ ] The policy works for required path parameters in buffered and streaming methods.
- [ ] Tests assert raw wire URLs through HTTPX.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
