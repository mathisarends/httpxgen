# Production-readiness PR tickets

This directory contains **43 independent English implementation tickets** from the audit of `mathisarends/httpxgen` at commit `cf3c9f496a5d8b70f5230bd2f4a8dfcc57f71828` (main, version 0.2.0). Each ticket is intended to provide sufficient context for a later agent to implement one focused PR.

## Audit evidence and limits

- The repository was cloned into the workspace and its generator, templates, normalization, selection, output handling, tests, and CI were inspected.
- All **134 existing tests passed** locally on Python 3.14.0 with HTTPX 0.28.1 and Pydantic 2.13.5; generator coverage was approximately **91%**.
- Additional isolated generated-package checks reproduced the behaviors documented in the tickets. Requests were exercised through HTTPX MockTransport; the filename defect was also checked with Starlette's multipart parser, and transport protocol assignment was checked with Mypy 2.4.0.
- The checked-in preview matched newly generated output. Ruff lint passed, while Ruff format failed for four files. The lockfile was inconsistent with the project version.
- There were no open GitHub issues or PRs at the time of inspection. These are local ticket documents, not remotely created GitHub issues.
- This is a record of confirmed findings, not a guarantee that no other defects exist. A particular API may only exercise a subset of these features.

## Priority and delivery

**P1** marks defects with a significant correctness, data mutation, request-targeting, or resource-lifecycle impact in affected clients. **P2** marks narrower contract, supported-feature, typing, or reproducibility defects. Applicability depends on the production API's actual OpenAPI contract.

Implement one ticket per focused PR. Start with the P1 defects applicable to the target API. Do not treat string-rendering assertions as sufficient evidence of runtime correctness: generate, import, and exercise the client. Rejecting an unsupported construct can be appropriate when the ticket explicitly permits it; silently emitting invalid or weakened code is not.

## Ticket list

| Ticket | Priority | PR objective |
| --- | --- | --- |
| [001](001-preserve-explicit-json-null-fields.md) | P1 | Preserve explicitly supplied null fields in JSON request bodies |
| [002](002-omit-unset-body-defaults.md) | P1 | Do not insert unset model defaults into partial JSON updates |
| [003](003-encode-root-json-null.md) | P1 | Send a JSON null body distinctly from an omitted request body |
| [004](004-avoid-operation-local-name-collisions.md) | P1 | Prevent generated local variables from overwriting operation arguments |
| [005](005-preserve-dot-path-segments.md) | P1 | Prevent dot-valued path parameters from changing the target route |
| [006](006-support-mixed-binary-success-responses.md) | P1 | Preserve all documented success branches when an operation supports binary responses |
| [007](007-close-streams-on-cancellation.md) | P1 | Close entered HTTP responses when streaming setup or validation is cancelled |
| [008](008-wrap-stream-read-failures.md) | P1 | Translate binary stream read failures into the generated client error hierarchy |
| [009](009-support-synchronous-binary-iterables.md) | P2 | Make declared Iterable[bytes] uploads work with the default async HTTPX transport |
| [010](010-give-upload-parts-filenames.md) | P1 | Emit file parts that servers recognize for bytes and file-handle upload shorthand |
| [011](011-serialize-multipart-object-fields.md) | P2 | Serialize multipart object fields as their declared JSON representation |
| [012](012-respect-urlencoded-body-encoding.md) | P2 | Honor Encoding Objects and nested values in URL-encoded form bodies |
| [013](013-preserve-nullable-component-schemas.md) | P1 | Preserve nullable component schemas in generated types and response parsing |
| [014](014-import-inline-oneof-validation-support.md) | P2 | Generate all imports and helpers required by inline oneOf annotations |
| [015](015-follow-reusable-references-during-tag-selection.md) | P1 | Compute tag-selected schema reachability through reusable OpenAPI components |
| [016](016-resolve-path-item-references-before-selection.md) | P2 | Resolve Path Item references without replacing inherited parameters with defaults |
| [017](017-share-discriminator-enum-dependencies.md) | P1 | Place discriminator enums with all models that depend on them in tag workspaces |
| [018](018-use-python-field-names-for-discriminators.md) | P1 | Map discriminator property names to their generated Python field names |
| [019](019-reserve-generated-client-method-names.md) | P2 | Reject collisions with constructors and generated streaming method names |
| [020](020-reserve-content-type-control-argument.md) | P2 | Disambiguate the content_type control argument from API parameters |
| [021](021-normalize-query-model-protected-fields.md) | P2 | Make query-model fields safe for Pydantic protected names and private attributes |
| [022](022-model-leading-underscore-properties.md) | P2 | Represent leading-underscore schema properties as actual Pydantic fields |
| [023](023-count-oneof-matches-without-coercion.md) | P2 | Evaluate oneOf branch matches using JSON Schema-compatible type semantics |
| [024](024-retain-scalar-and-item-schema-constraints.md) | P2 | Retain validation constraints on scalar components, container roots, and array items |
| [025](025-enforce-const-and-enum-intersection.md) | P2 | Apply const together with enum when rendering component schemas |
| [026](026-validate-json-request-body-inputs.md) | P2 | Validate JSON request inputs before serializing them |
| [027](027-reject-invalid-request-content-type.md) | P2 | Reject unsupported request content_type choices instead of sending an empty body |
| [028](028-preserve-binary-response-header-models.md) | P2 | Validate and expose declared response headers for binary success responses |
| [029](029-make-transport-protocol-type-compatible.md) | P2 | Make generated transport protocols statically compatible with httpx.AsyncClient |
| [030](030-emit-recursive-type-aliases-safely.md) | P2 | Generate recursive nonobject type aliases without import-time NameError |
| [031](031-treat-data-ref-keys-as-data.md) | P2 | Restrict reference normalization and validation to actual OpenAPI schema/reference positions |
| [032](032-allow-required-properties-with-default-annotations.md) | P2 | Allow required properties to carry default annotations without making them optional |
| [033](033-merge-headers-case-insensitively.md) | P2 | Merge configured and generated HTTP headers case-insensitively |
| [034](034-expose-api-error-body-convenience-values.md) | P2 | Keep ApiError.code and message useful when an error response declares headers |
| [035](035-detect-and-remove-obsolete-generated-files.md) | P2 | Detect obsolete generated files when package layout or tag selection changes |
| [036](036-synchronize-project-version-lockfile.md) | P2 | Update the lockfile metadata to match project version 0.2.0 |
| [037](037-restore-format-check-ci.md) | P2 | Restore the failing Ruff format check on main |
| [038](038-handle-nonobject-allof-safely.md) | P2 | Reject or faithfully model allOf compositions over scalar schemas |
| [039](039-enforce-required-names-without-properties.md) | P2 | Enforce required property names even when no property schema is declared |
| [040](040-support-query-allow-reserved.md) | P2 | Implement accepted allowReserved query parameters without a runtime signature error |
| [041](041-serialize-path-styles-correctly.md) | P2 | Implement path style delimiters and explode semantics correctly |
| [042](042-serialize-parameter-content-as-json.md) | P2 | Honor application/json content encoding for parameters |
| [043](043-implement-byte-format-base64.md) | P2 | Encode and decode OpenAPI byte-format fields as base64 |

## Related work

- **001 / 002 / 003:** JSON null values, omitted properties, and omitted whole bodies are distinct. These tickets touch the same serialization paths; coordinate their APIs and merge conflict resolution.
- **004 / 019 / 020 / 021 / 022:** Generated internal names, method names, control arguments, and Pydantic field names have different collision rules. Share helpers where useful but preserve each ticket's acceptance criteria.
- **006 / 007 / 008 / 028:** Binary success dispatch, lifecycle cleanup, read-error translation, and response headers overlap in streaming templates. Run all streaming regressions when changing those paths.
- **009 / 010 / 011 / 012 / 043:** Upload streaming, file-part metadata, structured form encodings, and base64 JSON fields must not be conflated with raw binary payloads.
- **015 / 016 / 017 / 018:** Reference resolution, tag reachability, generated dependency ownership, and discriminator aliases overlap in normalization/workspace generation.
- **014 / 023 / 024 / 025 / 030 / 032 / 038 / 039:** Schema annotation construction and validation semantics overlap. Retain correct JSON membership and presence rules when introducing Annotated, aliases, or validators.
- **036 / 037:** Small repository hygiene fixes. Keeping these separate makes their diffs easy to review and helps establish a reproducible green baseline.

## Repository implementation notes

- Follow `CLAUDE.md` and any applicable `AGENTS.md` instructions. At the audit baseline, `__init__.py` files use relative imports and other generator modules use absolute imports; avoid blanket module-level docstrings/comments.
- The source generator is under `httpxgen/generator/`; reusable generated source lives in Jinja templates under `httpxgen/generator/templates/`.
- Public generation entry points include `generate_client`, `generate_workspace`, and `write_client`. Test the appropriate single-client and tag-workspace paths.
- Public generated failures derive from `ClientError`: request preparation uses `RequestValidationError`, transport execution uses `TransportError`, invalid responses use `ResponseValidationError`, and API failures use `ApiError`. Preserve cancellation and borrowed transport ownership.
- Use temporary generated packages for regression tests. Fix source templates/generation logic, then regenerate the checked-in preview with the documented workflow when needed.
- Initial dependency setup can use `uv sync --frozen` to avoid accidentally rewriting the inconsistent lockfile before ticket 036. Run `uv run --frozen pytest --no-cov` and relevant lint/format checks. A failure already documented in ticket 037 must not be confused with a new regression.
- CI already runs tests for Python 3.12, 3.13, and 3.14. New generated Python code must work across that supported range.
- Tickets were added without implementing the production fixes. Re-check line locations and reproductions against the implementation branch before changing code.
