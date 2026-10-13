# 017: Place discriminator enums with all models that depend on them in tag workspaces

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Workspace ownership considers schema references but not generated discriminator-enum dependencies. A variant shared by two tags can be placed in shared.models while its discriminator enum stays in one tag's models module. Importing the package succeeds, but validation fails because the shared model's annotation is unresolved.

## Relevant code

- [httpxgen/generator/build.py](../httpxgen/generator/build.py), line 97 (shared_schemas)
- [httpxgen/generator/build.py](../httpxgen/generator/build.py), line 160 (_schema_owners)
- [httpxgen/generator/models.py](../httpxgen/generator/models.py), line 196 (_discriminator_enums)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Create discriminated union Choice of object variants A(kind='a') and B(kind='b'). Tag 'one' returns Choice; tag 'two' returns A directly. Generate a workspace for both tags. TypeAdapter(package.Choice).validate_python({'kind':'a'}) raises PydanticUserError that the adapter is not fully defined.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Include generated enum symbols in dependency/ownership analysis or move necessary discriminator enums to a module all dependent models can import safely.
- Avoid circular imports between shared and tag-specific modules.
- Consider variants participating in more than one union, rather than relying on the last union visited.

## Acceptance criteria

- [ ] The reproduced shared-variant workspace validates both union and direct variant responses.
- [ ] Generated enum dependencies are available without manual model_rebuild calls.
- [ ] Shared-only, tag-only, and multiply used variants produce deterministic importable output.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_build.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
