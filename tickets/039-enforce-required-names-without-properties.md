# 039: Enforce required property names even when no property schema is declared

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

JSON Schema allows required to mention property names without supplying schemas in properties. Rendering only declared properties loses that presence constraint, so generated validation accepts a missing required key.

## Relevant code

- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 303 (_render_component)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 388 (required property processing)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define component Entity={type:object,required:['id']} in OpenAPI 3.1, with additional properties allowed. The generated Entity.model_validate({}) currently succeeds. {'id':123} should be valid because presence is required but no value-type constraint was authored.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Preserve required-key presence independently of whether a typed property schema exists.
- Use a clear generated representation for unconstrained required values, or reject the unsupported shape explicitly before output.
- Check interaction with allOf, additionalProperties, and directional schema transformations.

## Acceptance criteria

- [ ] An empty object is rejected for the reproduced required-key schema.
- [ ] A present unconstrained id is accepted without inventing a type restriction.
- [ ] Constraints are not silently removed during normalization or composition.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_models.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
