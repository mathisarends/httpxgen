# 003: Send a JSON null body distinctly from an omitted request body

- **Priority:** P1
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

A valid root JSON null is currently passed as json=None. HTTPX interprets that argument as no JSON body, producing an empty payload with no JSON Content-Type. Optional body handling also uses None as the omission sentinel, making an explicit null body impossible to express.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 486 (_render_body)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 621 (_render_request_arguments)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate a required application/json request body whose schema is {type: [string, 'null']}. Call the operation with body=None and capture the request. The observed content is b'' instead of b'null'. Repeat with an optional nullable requestBody: the API currently cannot distinguish omission from explicitly sending null.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Represent optional-body omission independently of a valid JSON null value, with a readable generated API and documented behavior.
- For an explicitly supplied root null, emit the literal JSON payload and the selected JSON media type without relying on HTTPX's json=None sentinel.
- Handle application/json and +json media types, required and optional bodies, and media-type variants.

## Acceptance criteria

- [ ] A required nullable body of None sends b'null' with the correct Content-Type.
- [ ] An omitted optional body remains absent.
- [ ] An explicit null optional body can be expressed and sent without confusing omission.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
