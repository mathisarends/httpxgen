# 014: Generate all imports and helpers required by inline oneOf annotations

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Inline oneOf annotations use Annotated and _one_of, but client import generation does not import those symbols or ensure the validator exists in a support module. Accepted schemas thus fail at runtime. Python 3.14's deferred annotations can hide the defect until the request or response adapter is evaluated.

## Relevant code

- [httpxgen/generator/schema.py](../httpxgen/generator/schema.py), line 7 (schema_type)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 122 (_render_client_imports)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 477 (_one_of)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate an application/json request body, or a 200 JSON response, with schema {oneOf: [{type: string}, {type: integer}]}. Calling the request method yields RequestValidationError caused by NameError: Annotated is not defined; parsing the response yields ResponseValidationError with the same cause. Fixing only Annotated would still leave _one_of unresolved.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Ensure generated annotation expressions have all dependencies in the module where they are evaluated.
- Make the exact-oneOf helper available even when no component/model declaration currently causes render_models to emit it.
- Cover inline path/query/header/body/response positions where supported.

## Acceptance criteria

- [ ] Inline primitive oneOf bodies and responses work in an imported generated package.
- [ ] Every referenced helper is defined or imported; generated output passes meaningful type/name checks.
- [ ] The same tests run on Python 3.12, 3.13, and 3.14.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_build.py tests/generator/test_client.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
