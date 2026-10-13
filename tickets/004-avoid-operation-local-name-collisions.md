# 004: Prevent generated local variables from overwriting operation arguments

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Only a small set of signature names is reserved. Generated locals such as path, headers, cookies, and files overwrite same-named input arguments before serialization. This silently sends wrong values and, for a common multipart field named files, sends an empty upload.

## Relevant code

- [httpxgen/generator/operations.py](../httpxgen/generator/operations.py), line 262 (_validate_parameters)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 390 (_render_path)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 420 (_render_headers)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 581 (_render_multipart_body)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Four independently reproduced examples: /files/{path} with path='abc' sends /files/%2Ffiles%2F%7Bpath%7D; a required header argument named headers='abc' becomes an empty header; a cookie argument named cookies='abc' becomes empty; a required multipart binary-array field named files=[b'abc'] produces a zero-byte request.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Audit every local assignment in generated operations and streaming variants against all parameter/body-field names, including query-model locals and body_arguments.
- Prefer deterministic internal-name disambiguation or fail generation with an actionable message. Do not silently mutate inputs.
- Keep buffered forwarding arguments and multipart field signatures consistent with the chosen naming policy.

## Acceptance criteria

- [ ] The four reproduced cases either generate correctly functioning clients or fail before writing files with clear explanations.
- [ ] Add coverage for collisions between names in different locations and generated locals.
- [ ] No accepted operation silently overwrites a supplied value.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py tests/generator/test_client.py tests/generator/test_operations.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
