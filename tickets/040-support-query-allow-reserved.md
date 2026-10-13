# 040: Implement accepted allowReserved query parameters without a runtime signature error

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

Parameter parsing accepts allowReserved and code generation passes allow_reserved=True to serialize_query. That helper has no such argument. Any supplied query value for the feature raises RequestValidationError before the request is sent.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 860 (_serialize_call)
- [httpxgen/generator/templates/serialization.jinja2](../httpxgen/generator/templates/serialization.jinja2), line 45 (serialize_query)
- [httpxgen/generator/operations.py](../httpxgen/generator/operations.py), line 216 (_read_parameters)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Define required string query parameter q with allowReserved:true. Call run('a/b') with a generated client and HTTPX MockTransport. It raises RequestValidationError caused by TypeError: serialize_query() got an unexpected keyword argument 'allow_reserved'; the handler is never called.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Implement query reserved-character handling across helper generation and the actual HTTPX request construction, or reject the feature at generation time with an explicit limitation.
- Avoid claiming support merely by adding an unused keyword: params-based HTTPX encoding may still escape the characters.
- Keep delimiters and unsafe query syntax separate from parameter data.

## Acceptance criteria

- [ ] Accepted allowReserved parameters do not fail because of a helper signature mismatch.
- [ ] Actual raw URLs reflect the chosen documented reserved-character policy.
- [ ] Normal query escaping, arrays, and API-key query auth remain correct.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_client.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://spec.openapis.org/oas/v3.1.1.html#parameter-object)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
