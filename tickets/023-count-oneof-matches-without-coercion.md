# 023: Evaluate oneOf branch matches using JSON Schema-compatible type semantics

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

The exact-oneOf validator counts successful Pydantic adapters using default coercion. A JSON string containing digits also matches the integer adapter, so valid input is rejected as matching two branches. Boolean/integer and formatted-type cases need the same care.

## Relevant code

- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 477 (_one_of)
- [httpxgen/generator/schema.py](../httpxgen/generator/schema.py), line 7 (schema_type)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define component Choice with oneOf: [{type: string}, {type: integer}]. Return JSON string '123' from a 200 JSON response referencing Choice. It raises ResponseValidationError: expected exactly one oneOf variant, matched 2, although the JSON value is only a string.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Separate branch membership according to the source schema from any intentional post-selection Python conversion.
- Do not blindly enable strict validation in a way that rejects valid JSON date/UUID strings or integral JSON number semantics.
- Preserve the existing requirement that genuinely overlapping oneOf variants reject the value.

## Acceptance criteria

- [ ] '123' selects the string branch and integer JSON selects the integer branch.
- [ ] Boolean/integer cases and formatted string branches have correct JSON membership semantics.
- [ ] Values matching zero or more than one actual schema branch still fail.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_build.py tests/generator/test_models.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
