# 012: Honor Encoding Objects and nested values in URL-encoded form bodies

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

URL-encoded bodies are dumped into a mapping and handed to HTTPX without applying the specification's per-property encoding rules. Nested objects become Python dictionary strings, and array explode/style settings are ignored.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 519 (_render_body_variant)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 563 (_render_required_body)
- [httpxgen/generator/operations.py](../httpxgen/generator/operations.py), line 315 (_read_bodies)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Case A: tags is an array of strings with encoding.tags={style: form, explode: false}. A model with ['a','b'] currently sends tags=a&tags=b, instead of the nonexploded representation. Case B: point is an object {x:1,y:2}; the current body contains point=%7B%27x%27... (Python repr), not the declared form/object or JSON-content encoding.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Carry Encoding Object data into the operation generation model and serialize fields according to style, explode, allowReserved, and contentType where supported.
- Preserve repeated values with a transport-compatible representation and reject unsupported combinations explicitly.
- Apply the same implementation to required, optional, and media-type-variant form bodies.

## Acceptance criteria

- [ ] Exploded and nonexploded arrays produce their declared wire encodings.
- [ ] Nested object fields and JSON-encoded form properties are handled faithfully.
- [ ] Unsupported encoding combinations fail generation instead of silently producing Python repr.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py tests/generator/test_operations.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://spec.openapis.org/oas/v3.1.1.html#encoding-object)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
