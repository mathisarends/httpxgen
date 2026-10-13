# 037: Restore the failing Ruff format check on main

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

The existing CI run for the audited main commit is failing at Ruff format. Local ruff check succeeds, but ruff format --check reports four files requiring formatting. This is a release/merge hygiene failure, not evidence that the passing runtime tests are failing.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 354
- [httpxgen/generator/templates.py](../httpxgen/generator/templates.py), line 25
- [tests/generator/test_build.py](../tests/generator/test_build.py), line 315
- [tests/generator/test_improvements.py](../tests/generator/test_improvements.py), line 39
- .github/workflows/ci.yml

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

With frozen audit dependencies run uv run --frozen ruff format --check . It reports client.py, templates.py, test_build.py, and test_improvements.py as needing reformatting. The corresponding remote CI run is 34216823208.

## Implementation guidance

- Apply the configured formatter to the affected files without functional edits.
- Do not regenerate preview output unless formatting actually changes generator behavior/output.
- Keep this PR independent of lockfile synchronization and runtime bug fixes so the review remains simple.

## Acceptance criteria

- [ ] ruff format --check . and ruff check . both pass.
- [ ] The existing test suite still passes.
- [ ] The diff contains formatting-only changes and no unrelated artifacts.
- [ ] Demonstrate that the failing repository check now succeeds without changing generated-client runtime behavior.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run uv run --frozen ruff format --check ., uv run --frozen ruff check ., and uv run --frozen pytest --no-cov.

Read repository instructions before implementation. Keep this change limited to the repository hygiene problem described above. Do not combine it with generator behavior changes or unrelated dependency updates.

## References

- [Supporting specification or upstream source 1](https://github.com/mathisarends/httpxgen/actions/runs/34216823208)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
