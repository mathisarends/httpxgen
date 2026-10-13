# 016: Resolve Path Item references without replacing inherited parameters with defaults

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Path Item resolution merges a model_dump containing default parameters=[] over the referenced component, discarding inherited parameters even when no sibling parameters were authored. Tag discovery also ignores operations behind Path Item references.

## Relevant code

- [httpxgen/generator/operations.py](../httpxgen/generator/operations.py), line 197 (_resolve_path_item)
- [httpxgen/selection.py](../httpxgen/selection.py), line 46 (_operation_tags)
- [httpxgen/selection.py](../httpxgen/selection.py), line 56 (_paths_with_tags)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

In an OpenAPI 3.1 document define components.pathItems.Item with a required path parameter id and a tagged get operation. Set paths['/x/{id}'].$ref to that component. Untagged generation fails with missing path parameter id; filtering by the inherited 'items' tag instead reports that the tag does not exist.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Distinguish explicitly authored Path Item siblings from Pydantic defaults when resolving references.
- Make operation/tag selection inspect resolved Path Items, using a shared resolver where practical.
- Preserve supported local-reference behavior and reject unsupported or cyclic compositions clearly.

## Acceptance criteria

- [ ] A referenced Path Item retains its parameters and operations when no sibling override was authored.
- [ ] Inherited operation tags work with single-tag and workspace generation.
- [ ] Authored supported siblings have a deliberate tested merge policy.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_operations.py tests/test_selection.py tests/generator/test_build.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
