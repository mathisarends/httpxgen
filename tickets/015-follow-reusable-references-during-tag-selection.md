# 015: Compute tag-selected schema reachability through reusable OpenAPI components

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Tag filtering only collects direct schema references from selected paths and schemas. It does not traverse components.responses, requestBodies, parameters, or headers. Needed schemas are removed, while reusable components referring to removed schemas remain. Normalization then rejects an otherwise valid selected specification.

## Relevant code

- [httpxgen/selection.py](../httpxgen/selection.py), line 74 (_referenced_schemas)
- [httpxgen/selection.py](../httpxgen/selection.py), line 117 (_canonicalize_schema_names)
- [httpxgen/generator/normalize.py](../httpxgen/generator/normalize.py), line 275 (_validate_references)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define Thing in components.schemas and Ok in components.responses with a JSON $ref to Thing. A tagged operation uses responses.200.$ref=Ok. filter_operations_by_tags(spec,['items']) followed by generate_client fails with unresolved reference to Thing. Even an unused reusable response referencing an excluded schema can cause this failure. Canonicalizing a schema by title must also rewrite reusable-component references.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Traverse the local component reference graph with cycle protection, rather than scanning only schema-to-schema edges.
- Retain or prune non-schema components consistently with the selected operation graph.
- Rewrite references in all retained relevant components when canonical schema names change. Coordinate Path Item resolution with ticket 016.

## Acceptance criteria

- [ ] Single-tag and multi-tag generation work through reusable responses, request bodies, parameters, and headers.
- [ ] Unrelated reusable components do not leave dangling references.
- [ ] Schema-title canonicalization and cyclic reference graphs are handled deterministically.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/test_selection.py tests/generator/test_build.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
