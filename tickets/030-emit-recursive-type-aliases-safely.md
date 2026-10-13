# 030: Generate recursive nonobject type aliases without import-time NameError

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Recursive object fields benefit from deferred annotations, but generated assignment-style aliases are evaluated immediately. A recursive array or union alias references itself before it exists, producing an unimportable package despite the advertised recursive-type support.

## Relevant code

- [httpxgen/generator/schema.py](../httpxgen/generator/schema.py), line 60 (ordered_schemas)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 303 (_render_component)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Component Node={type:array,items:{$ref:'#/components/schemas/Node'}} emits Node = list[Node], which raises NameError at import. The finite-value-capable alias Node={anyOf:[{type:string},{type:array,items:{$ref:'#/components/schemas/Node'}}]} also raises NameError.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Use a suitable lazy/recursive alias representation supported by Python 3.12+ and Pydantic, or reject unsupported recursive alias shapes before writing code.
- Detect mutual recursion as well as self-reference; a topological sort cannot eliminate a true cycle.
- Preserve readable normal aliases and existing recursive object models.

## Acceptance criteria

- [ ] Supported self-recursive and mutually recursive alias packages import and validate finite values.
- [ ] Unsupported cases fail generation with a clear explanation, never import-time NameError.
- [ ] Existing recursive object/discriminator tests continue to pass.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_build.py tests/generator/test_schema.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
