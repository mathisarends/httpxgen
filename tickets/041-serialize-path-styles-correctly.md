# 041: Implement path style delimiters and explode semantics correctly

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

serialize_path applies one simple comma serializer to every style, percent-encodes the entire result, then adds a label/matrix prefix. This loses style-specific explode rules and encodes syntax delimiters as parameter data.

## Relevant code

- [httpxgen/generator/templates/serialization.jinja2](../httpxgen/generator/templates/serialization.jinja2), line 65 (serialize_path)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 860 (_serialize_call)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

For an array ['blue','black'], label+explode:true currently emits .blue%2Cblack instead of .blue.black; matrix+explode:true emits ;color=blue%2Cblack instead of ;color=blue;color=black. Simple nonexploded arrays also percent-encode their separator comma. Exercise objects and values containing literal delimiters separately.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Encode data values before joining them with the style's syntax delimiters.
- Implement scalar, array, and object expansion for supported simple/label/matrix combinations.
- Do not classify complex cookie form behavior as a normative bug without accounting for OpenAPI's documented ambiguity.

## Acceptance criteria

- [ ] Supported path styles match OpenAPI's style examples for scalar, array, and object values.
- [ ] Literal delimiter characters inside values are escaped distinctly from structural delimiters.
- [ ] Tests inspect raw HTTPX request paths and retain slash/percent escaping.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py tests/generator/test_client.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://spec.openapis.org/oas/v3.1.1.html#style-examples)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
