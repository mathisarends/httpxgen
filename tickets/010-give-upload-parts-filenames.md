# 010: Emit file parts that servers recognize for bytes and file-handle upload shorthand

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

The upload helper returns (None, content, None, {}) for bytes and BinaryIO shorthand, and UploadFile also defaults its filename to None. HTTPX consequently omits filename from Content-Disposition. Starlette parses the resulting part as a string form field rather than UploadFile, so ordinary file endpoints cannot consume the advertised shorthand.

## Relevant code

- [httpxgen/generator/templates/transport.jinja2](../httpxgen/generator/templates/transport.jinja2), line 52 (UploadFile)
- [httpxgen/generator/templates/transport.jinja2](../httpxgen/generator/templates/transport.jinja2), line 68 (upload_file_part)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate a required multipart/form-data file: {type: string, format: binary}. Call upload(b'abc'). The emitted part has Content-Disposition: form-data; name="file" and no filename. Feed that body to starlette.requests.Request.form(): the file value is str 'abc', not UploadFile. A bare file handle follows the same helper path.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Supply a safe fallback filename for file inputs and infer a basename from a file handle where appropriate.
- Preserve explicitly supplied filenames, content types, and headers. Define intentional filename=None behavior separately from accidental omission.
- Do not read file handles eagerly.

## Acceptance criteria

- [ ] Bytes, bare binary file handles, and default UploadFile inputs arrive as file parts in a real multipart parser.
- [ ] Explicit upload metadata is preserved.
- [ ] Repeated binary-array fields and lazy file reads continue to work.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_improvements.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://github.com/encode/starlette/blob/master/starlette/formparsers.py)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
