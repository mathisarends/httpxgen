# 038: Reject or faithfully model allOf compositions over scalar schemas

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

allOf is treated as object inheritance even when a referenced base is a scalar alias. The generator accepts the schema, emits a subclass of int, then response parsing calls model_validate on that non-Pydantic class. A valid response fails with an attribute error instead of generation rejecting the unsupported composition.

## Relevant code

- [httpxgen/generator/schema.py](../httpxgen/generator/schema.py), line 43 (split_all_of)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 303 (_render_component)
- [httpxgen/generator/operations.py](../httpxgen/generator/operations.py), line 509 (_response_model)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define Value={type:integer} and Count={allOf:[{$ref:'#/components/schemas/Value'},{minimum:1}]}. A 200 JSON response references Count. Generation/import succeed, but a valid response JSON 2 raises ResponseValidationError: type object Count has no attribute model_validate.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Resolve base schema kinds before choosing inheritance.
- Implement scalar intersection annotations if within scope, or reject nonobject allOf early with a precise unsupported-composition error.
- Preserve practical allOf inheritance between object models and existing conflict validation.

## Acceptance criteria

- [ ] The reproduced schema either validates its scalar intersection correctly or fails generation before files are written.
- [ ] No generated non-Pydantic scalar class is parsed using model_validate.
- [ ] Supported object inheritance remains unchanged.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_normalize.py tests/generator/test_build.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
