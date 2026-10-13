# 033: Merge configured and generated HTTP headers case-insensitively

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Headers are plain dictionaries and default/auth assignments use case-sensitive keys. Caller-supplied lowercase header names coexist with generated title-case equivalents. HTTPX emits duplicates instead of preserving one intentional value, which is particularly problematic for Content-Type and Authorization.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 420 (_render_headers)
- [httpxgen/generator/templates/serialization.jinja2](../httpxgen/generator/templates/serialization.jinja2), line 84 (apply_security)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Create a JSON response operation and construct the generated client with headers={'accept':'text/plain'}. The captured HTTPX request contains both accept:text/plain and accept:application/json. Add equivalent cases for a lowercase content-type on a request body and lowercase authorization when credentials are applied.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Use a transport-neutral case-insensitive merge policy while keeping generated source readable.
- Define precedence between caller headers, spec header parameters, media defaults, and security credentials.
- Do not silently combine conflicting Content-Type/Authorization values.

## Acceptance criteria

- [ ] Each logical header is emitted once regardless of input casing.
- [ ] Defaults respect configured values according to the documented policy.
- [ ] Auth and request-body headers have deterministic tested precedence.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
