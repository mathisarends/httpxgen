# 013: Preserve nullable component schemas in generated types and response parsing

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Referencing a nullable object component produces the model class alone, and the response generator chooses Model.model_validate instead of a nullable adapter. Valid JSON null responses are rejected. Nullability on a component represented as an object model is lost even though nullable values are advertised as supported.

## Relevant code

- [httpxgen/generator/schema.py](../httpxgen/generator/schema.py), line 7 (schema_type)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 303 (_render_component)
- [httpxgen/generator/operations.py](../httpxgen/generator/operations.py), line 509 (_response_model)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

For OpenAPI 3.0.3 define Thing as {type: object, nullable: true, properties: {id: {type: string}}}. Return it via a $ref in a 200 application/json response. A wire body b'null' raises ResponseValidationError. The valid OpenAPI 3.1 equivalent uses type: [object, 'null'] and reproduces the same failure.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Resolve effective component nullability when constructing annotations and choosing a response validation expression.
- Keep an object model available while representing the referenced nullable value faithfully, rather than making every model field optional.
- Do not treat arbitrary nullable annotations on schemas without the required OpenAPI 3.0 type semantics as proof that null must be accepted.

## Acceptance criteria

- [ ] Both valid version-specific object-null schemas accept JSON null through component references.
- [ ] Nonnull objects are still validated with all required properties and constraints.
- [ ] Nested references and request-body annotations preserve the same nullability.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_schema.py tests/generator/test_models.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
