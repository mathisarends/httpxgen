# 036: Update the lockfile metadata to match project version 0.2.0

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

pyproject.toml declares httpxgen 0.2.0 while the editable root package in uv.lock is still 0.1.0. A fresh uv sync --locked fails immediately because the lockfile requires updating, preventing a reproducible locked setup.

## Relevant code

- [pyproject.toml](../pyproject.toml), line 3
- [uv.lock](../uv.lock), line 182

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

At audit revision cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828 run uv sync --locked. It reports that uv.lock needs to be updated. uv sync --frozen was used only to execute the audit without editing the checked-in lockfile.

## Implementation guidance

- Regenerate lock metadata using the repository's intended uv workflow.
- Avoid unrelated dependency upgrades when only project metadata needs synchronization.
- Consider a locked consistency check in CI if useful, without mixing formatting or runtime fixes into this PR.

## Acceptance criteria

- [ ] A fresh uv sync --locked succeeds.
- [ ] The editable root package metadata agrees with pyproject.toml.
- [ ] Review the lock diff and explain any dependency changes instead of hiding them in the version repair.
- [ ] Demonstrate that the failing repository check now succeeds without changing generated-client runtime behavior.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run uv sync --locked and verify git diff -- uv.lock pyproject.toml contains only the intended changes.

Read repository instructions before implementation. Keep this change limited to the repository hygiene problem described above. Do not combine it with generator behavior changes or unrelated dependency updates.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
