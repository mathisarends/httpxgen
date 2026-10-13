# 011: Serialize multipart object fields as their declared JSON representation

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Nonfile multipart fields are passed through scalar(), which uses str(value). A structured field is therefore emitted as a Python/Pydantic repr rather than JSON, and its per-part media type is absent. MediaType encoding metadata is retained only as unprocessed extra data.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 581 (_render_multipart_body)
- [httpxgen/generator/operations.py](../httpxgen/generator/operations.py), line 315 (_read_bodies)
- [httpxgen/openapi.py](../httpxgen/openapi.py), line 23 (MediaType)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Use a required multipart metadata property whose schema is an object with required string name. Pass the generated metadata model with name='x'. The emitted part contains name='x' instead of {"name":"x"}, with no application/json part Content-Type. Also cover arrays of objects and an explicit encoding.metadata.contentType.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Serialize structured multipart fields according to OpenAPI's encoding defaults and explicit Encoding Objects.
- Preserve aliases and nested values; never use Python repr as a wire representation.
- Either support encoding options faithfully or reject unsupported ones before emitting a client.

## Acceptance criteria

- [ ] Object and object-array multipart fields contain valid JSON with the correct per-part Content-Type.
- [ ] Explicit encoding metadata is respected or rejected with an actionable generation error.
- [ ] Existing scalar fields and file parts retain their working behavior.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py tests/generator/test_operations.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://spec.openapis.org/oas/v3.1.1.html#special-considerations-for-multipart-content)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
