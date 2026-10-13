# 032: Allow required properties to carry default annotations without making them optional

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

The generator rejects a property that is both required and has a default. These keywords are not contradictory: required enforces presence, while default is an annotation. An existing test currently codifies this overly restrictive rejection.

## Relevant code

- [httpxgen/generator/normalize.py](../httpxgen/generator/normalize.py), line 421 (_validate_required_defaults)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 409 (_render_field)
- [tests/generator/test_normalize.py](../tests/generator/test_normalize.py), line 398

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Use an OpenAPI 3.1 object schema with required:[count] and properties.count={type:integer,default:1}. Generation fails with 'property is required and also declares a default; drop one of the two'. The desired generated model must still reject a missing count rather than filling it automatically.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Separate validation presence semantics from schema default annotations.
- Replace the test asserting rejection with coverage of supported generation and required validation.
- Do not introduce an automatic fallback that makes missing required properties valid; preserve optional-default handling deliberately.

## Acceptance criteria

- [ ] The valid reproduced schema generates successfully.
- [ ] Missing count is rejected while an explicitly supplied count is accepted.
- [ ] The default annotation does not weaken required validation or silently insert a required value.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_normalize.py tests/generator/test_models.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://json-schema.org/understanding-json-schema/reference/annotations)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
