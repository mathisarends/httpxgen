# 018: Map discriminator property names to their generated Python field names

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Variant fields are normalized to Python names and given wire aliases, but union Field(discriminator=...) still uses the raw wire propertyName. Pydantic expects the model field name, so common camelCase, punctuation, and keyword property names produce unusable discriminated unions.

## Relevant code

- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 333 (Field discriminator)
- [httpxgen/generator/naming.py](../httpxgen/generator/naming.py), line 23 (field_identifier)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define A and B with required kindType fields holding const 'a' and 'b'. Define Choice with discriminator.propertyName='kindType' and a matching mapping. The generated field is kind_type, yet validating {'kindType':'a'} through TypeAdapter(Choice) raises 'Model A needs a discriminator field for key kindType'. propertyName='type-name' also fails; a plain 'type' control works.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Use the same deterministic field-name mapping for discriminator configuration and variant declarations.
- Keep wire aliases intact so response parsing and request serialization still use the original property name.
- Handle keyword and protected-name normalization consistently.

## Acceptance criteria

- [ ] CamelCase, hyphenated, and keyword discriminator property names validate correctly.
- [ ] Both wire aliases and supported Python-name construction work.
- [ ] Existing discriminator enums and mapping validation remain intact.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_models.py tests/generator/test_build.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
