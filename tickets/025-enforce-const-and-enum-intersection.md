# 025: Apply const together with enum when rendering component schemas

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Component rendering selects the enum branch before considering const. A component authored with both constraints is broadened to all enum members, although valid values must satisfy their intersection. The generic schema_type helper already treats const differently, so root components and inline positions disagree.

## Relevant code

- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 303 (_render_component)
- [httpxgen/generator/schema.py](../httpxgen/generator/schema.py), line 7 (schema_type)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define Test={type:string,const:'a',enum:['a','b']}. Generate and import the package. TypeAdapter(package.Test).validate_python('b') currently succeeds, despite violating const.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Render the intersection of simultaneously authored constraints consistently in component and inline schemas.
- Detect empty/contradictory intersections with a clear generation error or a faithfully uninhabitable type.
- Preserve readable enum output where the enum remains the appropriate public representation.

## Acceptance criteria

- [ ] 'a' is accepted and 'b' is rejected in the reproduced schema.
- [ ] Component references and inline const-plus-enum schemas behave consistently.
- [ ] Numeric constants/enums and contradictory combinations are covered.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_models.py tests/generator/test_schema.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
