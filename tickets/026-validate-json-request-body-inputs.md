# 026: Validate JSON request inputs before serializing them

- **Priority:** P2
- **Status:** Ready for implementation
- **Intended delivery:** One focused pull request
- **Audit baseline:** `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0)
- **Evidence:** Reproduced in the production-readiness audit on 2026-10-13; no fix is included in this ticket.

## Problem

TypeAdapter.dump_python serializes a value but does not validate it against the input schema. Invalid mappings or mutated model values can therefore be sent despite the generated RequestValidationError boundary. The current typed signature alone does not enforce this at runtime.

## Relevant code

- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 519 (_render_body_variant)
- [httpxgen/generator/client.py](../httpxgen/generator/client.py), line 563 (_render_required_body)
- httpxgen/generator/templates/operation.jinja2

Line numbers refer to the audit baseline. Follow the named functions if later changes move them.

## Reproduction

Generate a required JSON body with required integer count and minimum:1. Call the generated method with {'count':'oops'} from a dynamically typed caller. The captured request currently sends {"count":"oops"} without RequestValidationError. Also cover a generated model whose field was mutated after construction.

For generated-runtime cases, follow the isolated-package pattern in `tests/generator/test_runtime.py` or `test_improvements.py`: generate into a temporary directory, import the emitted package, and capture real HTTPX requests with `httpx.MockTransport`. Add an `info` object with title/version and a unique `operationId` to minimal specs. Do not commit scratch generated packages.

## Implementation guidance

- Define and implement a clear runtime input-validation contract for generated JSON methods, validating before dumping when the value is not trustworthy.
- Keep valid model instances, aliases, discriminated unions, nullable values, and omission semantics correct.
- Avoid repeated validation that adds no value, but do not rely on serializer warnings as validation failures.

## Acceptance criteria

- [ ] Invalid input fails as RequestValidationError before the HTTP transport is called.
- [ ] Valid accepted inputs are serialized according to the declared schema.
- [ ] Required, optional, and multi-media JSON body paths share the same policy.
- [ ] Add a regression that fails on the audited behavior and verifies the generated client's externally observable result.
- [ ] Existing supported behavior and the relevant repository tests still pass.
- [ ] Update user-facing documentation when public signatures, supported scope, or wire behavior change.

## Validation

Run `uv run --frozen pytest --no-cov tests/generator/test_improvements.py tests/generator/test_runtime.py`, then the complete test suite once the change is ready. Use existing tests as a starting point; assertions about rendered strings alone are insufficient for a runtime defect.

Read repository instructions before implementation. Fix the generator/templates, rather than only a checked-in preview client. Regenerate `preview/` when output changes and verify its imports and relevant runtime behavior. The injected HTTP client is borrowed and must not be closed by the generated wrapper.

## Scope boundaries

Implement this ticket's behavior in one reviewable PR. Consult [the ticket index](README.md) for related work and overlapping files; do not silently absorb unrelated tickets. If a construct remains intentionally unsupported, reject it during generation with a specific actionable error and document the limitation rather than emitting incorrect code.
