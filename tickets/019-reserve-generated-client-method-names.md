# 019: Reject collisions with constructors and generated streaming method names

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

The method-name collision check only protects aclose, __aenter__, and __aexit__. An operation named __init__ overwrites the generated constructor. An explicit operation named stream_download overwrites the streaming companion generated for download, silently breaking buffered downloads as well.

## Relevant code

- [httpxgen/generator/package.py](../httpxgen/generator/package.py), line 41 (_CLIENT_METHODS)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 294 (binary method generation)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Case A: operationId='__init__' with a 204 response generates successfully, but constructing the client raises a positional-argument TypeError. Case B: /a has binary operationId='download' and /b has operationId='stream_download' with a 204 response. The class's stream_download becomes a coroutine instead of an async context-manager factory.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Build the complete generated method namespace before rendering, including constructors and all streaming companion methods.
- Fail early with the conflicting operations and generated symbol identified, or apply a documented deterministic disambiguation policy.
- Cover normalization collisions as well as authored names.

## Acceptance criteria

- [ ] Both reproduced specs are rejected before output is written or generate fully functioning disambiguated methods.
- [ ] No operation overwrites a lifecycle or companion method.
- [ ] Ordinary unique operation names remain unchanged.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_package.py tests/generator/test_build.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
