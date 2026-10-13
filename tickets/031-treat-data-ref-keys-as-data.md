# 031: Restrict reference normalization and validation to actual OpenAPI schema/reference positions

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Recursive reference walkers inspect arbitrary dictionaries and strings, including literal data in default/examples. A data object with a '$ref' key is mistaken for an OpenAPI Reference Object. This rejects valid specs and risks rewriting or stripping literal application data.

## Relevant code

- [httpxgen/generator/normalize.py](../httpxgen/generator/normalize.py), line 275 (_validate_references)
- [httpxgen/generator/normalize.py](../httpxgen/generator/normalize.py), line 362 (_strip_oas30_reference_siblings)
- [httpxgen/selection.py](../httpxgen/selection.py), line 99 (_schema_references)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define a model property metadata={type:object, default:{'$ref':'document-id'}}. Generation currently fails with 'only local component references are supported: document-id'. Use a valid 3.1 schema and add examples containing literal component-looking strings. The 3.0 sibling-stripping traversal should also be checked for corrupting such data.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Walk the OpenAPI/schema structure with context; default, example, and examples payloads are data, not schema documents.
- Keep real unresolved/external-reference checks and version-specific reference semantics intact.
- Do not rewrite literal strings solely because they resemble component references.

## Acceptance criteria

- [ ] The reproduced default and equivalent example payloads are preserved exactly.
- [ ] Real invalid references still fail with actionable errors.
- [ ] Tag selection and canonicalization never mutate literal application data.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_normalize.py tests/test_selection.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
