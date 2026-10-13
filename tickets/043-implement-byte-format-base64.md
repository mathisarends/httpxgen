# 043: Encode and decode OpenAPI byte-format fields as base64

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

format:byte is mapped to plain bytes, but Pydantic's default bytes JSON handling is UTF-8 rather than OpenAPI 3.0's base64 representation. ASCII input is sent without base64 encoding; arbitrary bytes can fail serialization; a base64 response string is returned as its encoded text bytes rather than decoded content.

## Relevant code

- [httpxgen/generator/schema.py](../httpxgen/generator/schema.py), line 115 (_string_type)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 519 (_render_body_variant)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 303 (_render_component)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Use an OpenAPI 3.0.3 JSON object with required data={type:string,format:byte}. A model value b'abc' should send 'YWJj', but the serializer emits 'abc'. b'\xff' fails UTF-8 dumping. A response {'data':'YWJj'} becomes b'YWJj' rather than b'abc'. The audit also observed the same legacy-format behavior in 3.1.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Use a suitable base64-aware annotation/configuration for byte-format fields without changing application/octet-stream or multipart binary fields.
- Handle encode and decode consistently in nested models, aliases, and component schemas.
- If supporting 3.1 contentEncoding:base64, treat its semantics deliberately instead of assuming every format:binary/bytes value is base64.

## Acceptance criteria

- [ ] Arbitrary binary input round-trips through valid base64 JSON strings.
- [ ] Response byte-format values are decoded correctly and invalid base64 follows a documented validation policy.
- [ ] Raw binary upload/download behavior remains unchanged.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_schema.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://spec.openapis.org/oas/v3.0.4.html#data-types)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
