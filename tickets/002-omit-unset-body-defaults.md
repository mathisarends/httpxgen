# 002: Do not insert unset model defaults into partial JSON updates

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

JSON bodies are dumped without exclude_unset. Optional properties with schema defaults are consequently transmitted even when the caller never supplied them. For partial updates this can change unrelated server state. This is separate from dropping explicit null values.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 519 (_render_body_variant)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 563 (_render_required_body)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate a PATCH operation with application/merge-patch+json and an object body containing optional name: [string, null] and enabled: {type: boolean, default: true}. Invoke it with the generated body model constructed as name=None. The captured body currently becomes {"enabled": true}: it updates an unrequested property. After ticket 001, the expected body is {"name": null}, without enabled.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Use Pydantic's supplied-field information to preserve the caller's intended update, including explicitly supplied values equal to their defaults.
- Choose and document an omission policy that is correct for partial-update media types and does not accidentally change ordinary create requests.
- Do not fix this by using exclude_defaults, which also removes explicitly supplied default values.

## Acceptance criteria

- [ ] Unset optional defaults do not appear in a merge-patch request.
- [ ] An explicitly supplied default value still appears on the wire.
- [ ] Nested models and aliased properties follow the same supplied-versus-unset rule.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://www.rfc-editor.org/rfc/rfc7396.html)
- [Supporting specification or upstream source 2](https://json-schema.org/understanding-json-schema/reference/annotations)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
