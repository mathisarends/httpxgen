# 022: Represent leading-underscore schema properties as actual Pydantic fields

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

A schema property such as _id is left as a leading-underscore Python attribute, which Pydantic treats as private. Required/type validation is therefore silently lost. With extra='allow' a supplied value may survive only as an untyped extra, masking the defect.

## Relevant code

- [httpxgen/generator/naming.py](../httpxgen/generator/naming.py), line 23 (field_identifier)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 303 (_render_component)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate a JSON response model with type: object, required: [_id], and properties._id.type: string. Returning {} is currently accepted instead of raising ResponseValidationError. Supplying an _id value does not establish an ordinary validated model field; also test additionalProperties:false.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Give leading-underscore wire properties safe public Python field names and explicit aliases.
- Detect collisions introduced by the chosen renaming policy.
- Keep protected model_ naming and existing aliases compatible.

## Acceptance criteria

- [ ] Missing required _id is rejected.
- [ ] The supplied property is type-validated and exposed through a documented Python field name.
- [ ] Serialization uses the exact _id wire alias with both extra allow and forbid models.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_naming.py tests/generator/test_models.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
