# Changelog

## Unreleased

## 0.3.0 — 2026-10-13

### Migration from 0.2.0

- Regenerate clients and update consumers together: binary responses with declared headers now return typed result models. Read bytes from `result.body`; streaming result models expose `result.body.iter_bytes()`.
- Omit an optional JSON body argument to send no body. Explicit `None` now sends JSON null when the schema permits it and raises `RequestValidationError` otherwise; the default is the generated `UNSET` sentinel.
- Leading-underscore model properties use public Python field names (for example, `_id` becomes `field_id`); query parameters beginning with `_` or `model_` also use safe public names. Wire aliases remain unchanged.
- String `format: byte` values now use standard Base64 on the JSON wire. Supply decoded Python bytes or valid Base64 strings; invalid response strings raise `ResponseValidationError`.
- JSON request inputs and supported schema constraints are validated more consistently, and exact `oneOf` membership no longer uses string/number/boolean coercion. Previously accepted invalid data can now fail validation.

### Changed

- Optional JSON body arguments distinguish omission from explicit null; request inputs and supported schema constraints are validated before transport.
- Regeneration removes obsolete modules carrying the generator header, while preserving handwritten files; `--check` reports obsolete modules without removing them.
- CI now requires locked dependencies and checks generated transport and operation typing against HTTPX and HTTPX2.

### Fixed

- Preserve and validate declared headers on empty success responses in operations that also return binary content, for both buffered and streaming methods.
- Deserialize array response headers before validating their schema, retaining array/item constraints, nullable arrays, and referenced schema aliases.

### Production-readiness fixes

#### Ticket 043 — Encode byte-format JSON as Base64

- Use a Base64-aware bytes annotation for legacy byte-format fields and aliases, encoding arbitrary Python bytes and strictly decoding Base64 strings.
- Keep raw binary bodies and multipart files unchanged; document invalid-Base64 response validation.
- Added real HTTPX round trips for nested/aliased/component/root byte values, invalid strings, raw binary/multipart behavior, and generated static typing; regenerated the preview.

#### Ticket 042 — Honor JSON parameter content

- Retain selected parameter content encoding and serialize query/header/path values as compact JSON with validation, aliases, and formatted/null values.
- Normalize inline and reusable parameter content schemas; reject multiple media types, incompatible style options, and unsupported JSON cookie content explicitly.
- Added real HTTPX wire regressions for inline/reusable parameters, object aliases, dates, and null/omission behavior; regenerated the preview.

#### Ticket 041 — Correct path style delimiters and explode

- Encode individual path values before adding simple/label/matrix syntax and implement exploded array/object expansions.
- Escape literal delimiters independently, retain dot-segment protection, and reject query-only allowReserved on other locations.
- Added raw HTTPX path regressions for scalar/array/object styles and slash/percent/literal-delimiter data; regenerated the preview.

#### Ticket 040 — Serialize allowReserved query values

- Accept the reserved-query helper option and construct affected request URLs without HTTPX re-escaping the expanded values.
- Preserve query-safe reserved characters and encoded triples while escaping query delimiters, plus signs, and unsafe characters.
- Added raw HTTPX URL checks covering optional values, ordinary escaping, repeated arrays, and API-key query authentication; regenerated the preview.

#### Ticket 039 — Enforce required keys without property schemas

- Generate presence validators for undeclared/inherited required keys without inventing value types or bypassing additional-property validation.
- Preserve undeclared required keys when creating request/response schema variants.
- Added request/response, inheritance, directional, typed-extra, and forbidden-extra regressions.

#### Ticket 038 — Reject nonobject allOf compositions

- Resolve referenced base kinds before accepting object inheritance; reject scalar/array intersections and incompatible nullable/union bases before writing output.
- Added generation-failure regressions and a real HTTPX response test preserving supported object inheritance.

#### Ticket 036 — Synchronize editable project lock metadata

- Update the lockfile root version from 0.1.0 to 0.2.0 without changing dependencies.
- Require locked dependency installation in CI so metadata drift fails visibly.
- Verified a fresh locked environment installation and reviewed the one-line lockfile diff.

#### Ticket 035 — Reconcile obsolete generated modules

- Detect old generated modules after layout/tag changes in check mode and remove them during regeneration.
- Limit cleanup to files with the generator header inside the output package; preserve handwritten/binary assets and unmanaged package markers.
- Added a workspace-to-single-client regression checking read-only stale detection and obsolete import removal.

#### Ticket 034 — Expose ApiError payload convenience values

- Mark generated response wrappers explicitly and read `ApiError.code`/`message` from their typed payload while keeping header and compatibility accessors intact.
- Avoid unwrapping arbitrary dictionary/model payloads merely because they contain `body`.
- Added header/no-header error and dictionary-detail regressions; regenerated the preview.

#### Ticket 033 — Merge headers case-insensitively

- Deduplicate configured headers and use case-insensitive defaults/replacements for media headers, operation parameters, and credentials.
- Document precedence: configured values override defaults, operation parameters override configuration, and credentials override both.
- Added real HTTPX header multiplicity/precedence regressions; regenerated the preview.

#### Ticket 032 — Allow required properties with default annotations

- Permit required/default combinations while retaining presence validation; preserve the default as JSON Schema metadata rather than an automatic model fallback.
- Keep optional-default behavior and replace the old rejection test with supported generation and runtime presence checks.

#### Ticket 031 — Treat data $ref keys as data

- Share an OpenAPI-context walker for reference validation, rewriting, dependency analysis, and version-specific normalization.
- Preserve literal defaults, examples, enum/const values, and example payloads; real references and discriminator mappings retain validation/canonicalization.
- Added 3.0/3.1 and tag-selection runtime regressions, genuine property-name/reference checks, and invalid-reference rejection.

#### Ticket 030 — Emit recursive type aliases safely

- Detect self/mutual schema cycles and emit lazy Python 3.12+ aliases for recursive nonobject types while preserving ordinary aliases and object models.
- Reject unsupported recursive exact-oneOf aliases during generation.
- Added imported runtime validation for recursive arrays/unions and mutual aliases.

#### Ticket 029 — Make transport protocols statically compatible

- Use read-only response properties, accurate async context-manager exit types, and explicit supported request/stream arguments compatible with HTTPX.
- Pass query pairs as immutable tuples and fix generated serialization helper annotations.
- Add a Mypy consumer regression that also checks ordinary and binary-header generated operation code, and run it explicitly in CI.
- Verify protocol assignment against both HTTPX 0.28.1 and HTTPX2 2.13.1 without casts.

#### Ticket 028 — Preserve binary response header models

- Buffered binary responses with declared headers return the ordinary typed result model; streaming variants yield a typed stream result with a `BinaryStream` body.
- Reuse ordinary header extraction/validation before yielding and keep header-free binary methods unchanged and incremental.
- Added valid/malformed binary-header runtime regressions and documented the result interfaces.

#### Ticket 027 — Reject invalid request content_type choices

- Validate media-selection values before body dispatch, including omitted optional bodies; report supplied and valid choices in `RequestValidationError` without sending a request.
- Added required/optional and buffered binary runtime regressions for invalid and valid choices.

#### Ticket 026 — Validate JSON request body inputs

- Validate declared JSON input types before serialization and transport, including mappings and mutated generated models.
- Revalidate generated model instances while preserving aliases, explicit nulls, unset fields, and nested validation.
- Added required/optional/media-variant pre-transport regressions; regenerated the preview.

#### Ticket 025 — Enforce const/enum intersections

- Render component const constraints consistently with inline schemas, retaining the intersection with enum and rejecting contradictory combinations.
- Keep enum-only components readable and avoid invalid enum-member defaults for const aliases.
- Added string/numeric component/inline runtime and contradiction regressions.

#### Ticket 024 — Retain scalar, root-container, and item constraints

- Carry supported numeric/string/container constraints in reusable `Annotated` types, including scalar components and nested array items.
- Import annotation dependencies in inline operation modules while retaining readable direct model fields.
- Added scalar/root/item runtime validation regressions and regenerated the preview.

#### Ticket 023 — Count oneOf matches without coercion

- Determine oneOf branch membership with strict JSON validation, preserving formatted strings and integral JSON number semantics.
- Continue rejecting zero or overlapping matches.
- Added numeric-string, integer/boolean, integral-number, formatted-string, and overlap regressions; regenerated the preview.

#### Ticket 022 — Model leading-underscore properties

- Give leading-underscore schema properties public Python names with explicit wire aliases, retaining required/type/constraint validation.
- Reject collisions introduced by the prefix policy.
- Added runtime regressions for additional-property allow/forbid models and regenerated the preview.

#### Ticket 021 — Normalize protected/private query fields

- Prefix protected `model_` query names and leading-underscore names with safe public field names throughout signatures, models, construction, and access.
- Preserve exact wire names and required/constraint validation; normalized collisions still fail early.
- Added protected/private query runtime regressions.

#### Ticket 020 — Reserve the content_type control argument

- Reject API parameters that collide with the generated media-selection argument on operations offering multiple request media types.
- Preserve ordinary `content_type` API parameters when no control argument is generated.
- Added pre-write rejection and working single-media runtime regressions.

#### Ticket 019 — Reserve all generated client method names

- Reject operations that collide with constructors, lifecycle methods, or generated streaming companions before writing output.
- Added constructor and normalized companion-name collision regressions.

#### Ticket 018 — Use Python field names for discriminators

- Configure Pydantic discriminators with the same normalized Python field names used by variant models, retaining original wire aliases.
- Added request/response regressions for camelCase, punctuation, keywords, protected names, and ordinary discriminator properties.

#### Ticket 017 — Share discriminator enum dependencies

- Include generated discriminator-enum dependencies in workspace model ownership and promote dependencies to shared modules when needed.
- Choose discriminator enum dependencies deterministically for variants participating in multiple unions.
- Added shared/direct/multiple-union runtime regressions without manual model rebuilding.

#### Ticket 016 — Resolve Path Item references before selection

- Resolve local Path Item chains before normalization/tag selection, preserving inherited parameters when no override was authored.
- Explicit siblings replace corresponding inherited fields; cyclic references fail generation.
- Added untagged/single-tag/workspace runtime regressions, sibling overrides, and cycle rejection.

#### Ticket 015 — Follow reusable references during tag selection

- Traverse the reusable component graph with cycle protection and retain the schemas, request bodies, responses, parameters, and headers needed by selected operations.
- Prune unused reusable components and rewrite their references when canonicalizing schema titles.
- Added imported single-tag/workspace regressions with recursive schemas and reusable request/response/header/parameter components.

#### Ticket 014 — Import inline oneOf validation support

- Import `Annotated` and the exact-oneOf helper wherever inline operation annotations are evaluated.
- Emit the helper even when only inline request/response schemas require it.
- Added imported-client regressions across primitive path/query/header/body/response positions.

#### Ticket 013 — Preserve nullable component references

- Carry effective nullability through component references, aliases, nested fields, and request/response annotations while keeping object validation intact.
- Validate nullable object responses through a nullable adapter; ignore OpenAPI 3.0 nullable annotations without an explicit type.
- Added generated-client regressions for valid 3.0/3.1 schemas, null/non-null values, required properties, and constraints.

#### Ticket 012 — Respect URL-encoded body encodings

- Honor per-property array explode/style and JSON content encoding, with JSON defaults for structured values and explicit form serialization for flat objects.
- Emit encoded bytes with the form Content-Type so repeated values work with async HTTPX; reject unsupported encoding options.
- Added required/optional/media-variant runtime regressions and regenerated the preview.

#### Ticket 011 — Serialize multipart object fields as JSON

- Encode objects and object-array items as JSON parts with aliases and correct media types; respect JSON/+json contentType metadata and file content types.
- Reject unsupported multipart encoding options during generation.
- Added real multipart-parser regressions and regenerated the preview.

#### Ticket 010 — Give upload file parts filenames

- Bytes/default `UploadFile` inputs use a fallback filename; bare handles use their basename without eager reads.
- Preserve explicit filenames, media types, and headers; explicit `filename=None` intentionally produces a filename-less part.
- Added multipart-parser regressions for shorthand, metadata, and repeated files; regenerated the preview.

#### Ticket 009 — Support synchronous binary upload iterables

- Adapt synchronous binary iterables lazily to async-compatible chunks, preserving bytes and async iterables.
- Upload generator failures retain their cause in `TransportError`.
- Added lazy-consumption and runtime upload regressions for protocol/HTTPX modes and required/optional bodies; regenerated the preview.

#### Ticket 008 — Wrap binary stream read failures

- Buffered and streaming binary reads now raise `TransportError`, preserving the original cause and exception chain.
- Consumer exceptions and cancellation remain unchanged; response cleanup still runs.
- Added mid-download failure regressions and regenerated the preview.

#### Ticket 007 — Close streaming responses on cancellation

- Put the entire entered response lifetime under unconditional async context cleanup, including validation and error-body reads before yield.
- Preserve cancellation unchanged and keep the borrowed transport open.
- Added cancellation regressions before/after yield that verify response closure exactly once.

#### Ticket 006 — Support mixed binary success responses

- Preserve every declared successful representation in buffered and streaming methods, including JSON/text alongside binary content and empty 204 responses.
- Keep exact-status precedence over ranges and incremental binary downloads.
- Added generated-client status/media dispatch regressions and regenerated the preview.

#### Ticket 005 — Preserve dot-valued path segments

- Encode standalone dot segments so HTTPX preserves the intended route.
- Added wire-URL regressions for interior/trailing identifiers, buffered/streaming methods, dots, slashes, percent signs, and ordinary values; regenerated the preview.

#### Ticket 004 — Avoid operation argument/local collisions

- Disambiguate API parameter and multipart argument names that collide with generated locals or serialization helpers using an `_arg` suffix, preserving wire names.
- Added a real HTTPX regression covering path, header, cookie, query, helper names, and a multipart `files` array.

#### Ticket 003 — Distinguish JSON null bodies from omission

- Required and explicit optional root null bodies send literal `null` with the selected JSON Content-Type.
- Optional JSON body arguments use a separate omission sentinel; leaving out the argument sends no body.
- Covered required/optional bodies and JSON media variants with real HTTPX requests; regenerated the preview.

#### Ticket 002 — Omit unset defaults from JSON Merge Patch

- Merge patches serialize only explicitly supplied fields, recursively and by alias; explicit default values and null deletion instructions remain present.
- Ordinary JSON requests retain their existing non-null default behavior.
- Added a generated-client regression for explicit defaults and nested aliases.

#### Ticket 001 — Preserve explicit JSON null fields

- JSON request serialization preserves explicit nulls, including nested and aliased fields, while omitting unset nullable fields.
- Ordinary request models continue to send non-null schema defaults. JSON Merge Patch default omission is handled separately by ticket 002.
- Added generated-client HTTPX regressions for required/optional bodies and media variants; regenerated the preview.

#### Ticket 037 — Restore Ruff format checks

- Apply the configured formatter to the four files failing the baseline CI format check, without runtime changes.
- Delivered before the runtime stack so every PR can pass lint and format checks.
- Verified all 134 baseline tests, Ruff lint/format, and unchanged generated preview output.

## 0.2.0 — 2026-09-08

### Added

- Configurable generated HTTP backends through `--http-client`: transport-neutral `protocol` (default), concrete `httpx`, or concrete `httpx2` imports.
- Incremental binary downloads through `stream_<operation>()`, with `BinaryStream` metadata and buffered convenience methods.
- Binary upload iterable inputs and multipart uploads from bytes, open files, or `UploadFile`, including repeated file fields and explicit part metadata.
- A generated `ClientError` hierarchy with `TransportError`, `RequestValidationError`, `ResponseValidationError`, and typed `ApiError` details.

### Changed

- Default single-client names use the final package segment; `--client-name` provides an explicit public class name. Regenerating a dotted package can change the class consumers import.
- Generated clients borrow the supplied HTTP transport; closing the wrapper leaves that transport open.
- Generated sources are rendered through Jinja templates, and CI checks lint, formatting, and preview freshness.
- Package metadata now includes the MIT license and a descriptive summary.

## 0.1.0 — 2026-09-04

- Initial release of the typed async OpenAPI client generator.
