# 029: Make generated transport protocols statically compatible with httpx.AsyncClient

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

The default protocol backend is advertised as accepting HTTPX without casts, but a type checker rejects the normal AsyncClient and Response. HttpResponse.headers is a writable Mapping attribute, incompatible with HTTPX's concrete Headers attribute; request and stream/context-manager signatures also have structural conflicts.

## Relevant code

- [httpxgen/generator/templates/transport.jinja2](../httpxgen/generator/templates/transport.jinja2), line 15 (HttpResponse)
- [httpxgen/generator/templates/transport.jinja2](../httpxgen/generator/templates/transport.jinja2), line 33 (AsyncResponseContextManager)
- [httpxgen/generator/templates/transport.jinja2](../httpxgen/generator/templates/transport.jinja2), line 40 (AsyncHttpClient)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate a minimal protocol-backend package typed_api. In check.py instantiate TypedApiClient(httpx.AsyncClient(),'https://example.test'), assign an AsyncClient to AsyncHttpClient, and assign httpx.Response(200) to HttpResponse. Mypy 2.4.0 with HTTPX 0.28.1 reports three incompatible-type errors. Runtime isinstance checks do not prove static assignability.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Use read-only response properties where mutation is unnecessary and protocol signatures that describe the actual supported call surface.
- Correct the async context-manager exit typing instead of broad object varargs that concrete implementations cannot satisfy.
- Add meaningful static compatibility validation. Verify httpx2 too if available and claimed; do not claim it is tested without actually checking.

## Acceptance criteria

- [ ] The minimal HTTPX consumer type-checks without Any casts or adapters.
- [ ] Generated operation code also type-checks against its protocols.
- [ ] Concrete httpx/httpx2 backend generation remains usable and runtime transport borrowing is preserved.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_build.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://www.python-httpx.org/async/)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
