# 042: Honor application/json content encoding for parameters

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

A Parameter Object using content:application/json is reduced to its schema and then serialized with ordinary style/explode helpers. The chosen content encoding is forgotten, so a JSON object parameter is expanded into unrelated query keys rather than one encoded JSON value.

## Relevant code

- [httpxgen/generator/operations.py](../httpxgen/generator/operations.py), line 216 (_read_parameters)
- [httpxgen/generator/templates/serialization.jinja2](../httpxgen/generator/templates/serialization.jinja2), line 45 (serialize_query)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define query parameter coordinates with content.application/json.schema as an object containing numeric lat and long. Calling the generated method with {'lat':1,'long':2} sends ?lat=1&long=2 instead of a coordinates parameter containing a serialized JSON object. Normalization of inline content schemas also needs attention.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Represent the parameter's selected content encoding in the generation model instead of treating it as a schema-style parameter.
- Use the correct JSON serialization and wire-name preservation for supported locations.
- Reject unsupported content media types/combinations clearly rather than silently falling back to form/simple.

## Acceptance criteria

- [ ] A JSON query parameter is one correctly named parameter containing valid JSON.
- [ ] Aliases, formatted values, nullable values, and supported header/cookie content positions are handled deliberately.
- [ ] Ordinary schema/style parameters retain their behavior.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_operations.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://spec.openapis.org/oas/v3.1.1.html#parameter-object-examples)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
