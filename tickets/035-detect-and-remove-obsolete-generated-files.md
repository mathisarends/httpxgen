# 035: Detect obsolete generated files when package layout or tag selection changes

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Output checking compares only newly rendered paths. Old generated modules are neither detected nor removed when a workspace changes shape. --check can claim output is current while obsolete clients remain importable in the output directory.

## Relevant code

- [httpxgen/output.py](../httpxgen/output.py), line 65 (_changed_files)
- [httpxgen/output.py](../httpxgen/output.py), line 73 (_managed_output)
- tests/test_output.py

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate a two-tag workspace for one/two into the same package directory. Then regenerate as a single-tag client for one. The old two/client.py remains. Calling write_client(...,check=True) with the single-tag specification succeeds despite the obsolete generated files.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Track the exact managed output set and identify obsolete generated paths within the designated package directory.
- Check mode must report stale files without mutation; write mode should reconcile obsolete generated output safely.
- Preserve handwritten files and packages. Never recursively delete unrelated or unmanaged files.

## Acceptance criteria

- [ ] --check fails when obsolete generated modules remain.
- [ ] Regeneration removes/reconciles only safely identified obsolete generated files.
- [ ] Handwritten modules and preserved unmanaged __init__.py/py.typed files remain protected.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/test_output.py tests/test_cli.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
