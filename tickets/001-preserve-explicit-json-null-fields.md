# 001: Preserve explicitly supplied null fields in JSON request bodies

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Both JSON serialization paths use TypeAdapter.dump_python(..., exclude_none=True). A generated model containing an explicitly supplied nullable field loses that field on the wire. A required nullable property is therefore sent as an invalid object, and a JSON Merge Patch deletion instruction disappears.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 519 (_render_body_variant)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 563 (_render_required_body)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Use a required application/json object body with required: [name] and properties.name.type: [string, 'null']. Construct the generated body model with name=None and capture the request with httpx.MockTransport. The current wire body is {} instead of {"name": null}. Also exercise application/merge-patch+json: an explicitly supplied name=None must remain a deletion instruction.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Distinguish a field omitted by the caller from a field explicitly assigned None. Do not use exclude_none=True as a general JSON-body policy.
- Cover required, optional, nested, and aliased nullable fields in every JSON body path, including optional bodies and media-type variants.
- Coordinate with ticket 002, which addresses unsolicited default values, and ticket 003, which addresses a null value for the entire body.

## Acceptance criteria

- [ ] A required nullable property set to None is present as JSON null.
- [ ] An explicit nullable property in a merge patch is transmitted as null, including nested and aliased properties.
- [ ] No incidental None defaults are inserted for genuinely omitted properties.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://www.rfc-editor.org/rfc/rfc7396.html)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
