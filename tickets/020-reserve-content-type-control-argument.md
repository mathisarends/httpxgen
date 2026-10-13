# 020: Disambiguate the content_type control argument from API parameters

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Operations with multiple request media types add a keyword-only content_type argument, but parameter validation does not reserve that name for those operations. An accepted API parameter named content_type produces invalid Python with a duplicate function argument.

## Relevant code

- [httpxgen/generator/operations.py](../httpxgen/generator/operations.py), line 262 (_validate_parameters)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 269 (content_type signature)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define a required query parameter named content_type, plus a required requestBody offering application/json and text/plain string schemas. Generation succeeds; importing the generated package raises SyntaxError: duplicate argument 'content_type' in function definition.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Compute reserved control names from the actual generated signature, including media-type choices.
- Prefer clear deterministic disambiguation or an actionable GenerationError before file writes.
- Apply the rule consistently to buffered signatures and streaming forwarding calls.

## Acceptance criteria

- [ ] The reproduced client is either valid and callable or rejected before writing files.
- [ ] Multi-media operations without conflicts keep their current public signature.
- [ ] Error messages identify the API parameter and generated control argument.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_operations.py tests/generator/test_build.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
