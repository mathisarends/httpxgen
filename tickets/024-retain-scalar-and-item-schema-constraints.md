# 024: Retain validation constraints on scalar components, container roots, and array items

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Constraints are emitted for direct model fields, but scalar component aliases, root containers, and item schemas lose them. Generated response validation accepts values that violate straightforward supported constraints, weakening the promised typed contract.

## Relevant code

- [httpxgen/generator/schema.py](../httpxgen/generator/schema.py), line 98 (_plain_type)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 303 (_render_component)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 409 (_render_field)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Three confirmed cases: component Count={type: integer, minimum:10} accepts response -1; a model field xs={type:array,items:{type:integer,minimum:10}} accepts xs=[-1]; a component array with minItems:2 accepts []. Use generated packages and TypeAdapter or a JSON-response MockTransport.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Carry supported constraints into reusable annotations, for example Annotated/Field, rather than attaching them only to outer model attributes.
- Apply constraints at their authored schema level and maintain numeric/string/container distinctions.
- For unsupported validation keywords, prefer explicit rejection over silently claiming validation.

## Acceptance criteria

- [ ] All three invalid examples fail response/model validation.
- [ ] Valid scalar aliases and nested constrained arrays still parse and serialize correctly.
- [ ] Minimum/maximum, string constraints, and container lengths have targeted coverage where supported.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_schema.py tests/generator/test_models.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
