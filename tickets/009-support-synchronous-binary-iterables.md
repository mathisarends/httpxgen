# 009: Make declared Iterable[bytes] uploads work with the default async HTTPX transport

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

BinaryContent explicitly accepts bytes, Iterable[bytes], and AsyncIterable[bytes], but the generated client passes a synchronous iterable directly to httpx.AsyncClient. HTTPX rejects it as a synchronous request before sending anything.

## Relevant code

- [httpxgen/generator/templates/transport.jinja2](../httpxgen/generator/templates/transport.jinja2), line 12 (BinaryContent)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 621 (_render_request_arguments)

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate a required application/octet-stream body. Invoke the generated operation with body=iter([b'a', b'b']) using httpx.AsyncClient and MockTransport. It raises TransportError whose cause says 'Attempted to send an sync request with an AsyncClient instance.' No request reaches the handler.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Adapt accepted synchronous iterables to an async-compatible stream without eagerly concatenating them, or deliberately narrow the API and documentation if compatibility cannot be provided.
- Keep bytes and async iterables working and preserve chunk boundaries/lazy consumption.
- Check concrete backend modes as well as the default protocol mode.

## Acceptance criteria

- [ ] Every advertised BinaryContent input works with the default HTTPX async transport, or generation/API documentation consistently excludes unsupported inputs.
- [ ] A large iterable is consumed lazily.
- [ ] Input-generator failures have a deliberate, tested exception policy.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_improvements.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## References

- [Supporting specification or upstream source 1](https://www.python-httpx.org/async/)

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
