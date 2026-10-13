# Changelog

## Unreleased

### Ticket 014 — Import inline oneOf validation support

- Import `Annotated` and the exact-oneOf helper wherever inline operation annotations are evaluated.
- Emit the helper even when only inline request/response schemas require it.
- Added imported-client regressions across primitive path/query/header/body/response positions.

### Ticket 013 — Preserve nullable component references

- Carry effective nullability through component references, aliases, nested fields, and request/response annotations while keeping object validation intact.
- Validate nullable object responses through a nullable adapter; ignore OpenAPI 3.0 nullable annotations without an explicit type.
- Added generated-client regressions for valid 3.0/3.1 schemas, null/non-null values, required properties, and constraints.

### Ticket 012 — Respect URL-encoded body encodings

- Honor per-property array explode/style and JSON content encoding, with JSON defaults for structured values and explicit form serialization for flat objects.
- Emit encoded bytes with the form Content-Type so repeated values work with async HTTPX; reject unsupported encoding options.
- Added required/optional/media-variant runtime regressions and regenerated the preview.

### Ticket 011 — Serialize multipart object fields as JSON

- Encode objects and object-array items as JSON parts with aliases and correct media types; respect JSON/+json contentType metadata and file content types.
- Reject unsupported multipart encoding options during generation.
- Added real multipart-parser regressions and regenerated the preview.

### Ticket 010 — Give upload file parts filenames

- Bytes/default `UploadFile` inputs use a fallback filename; bare handles use their basename without eager reads.
- Preserve explicit filenames, media types, and headers; explicit `filename=None` intentionally produces a filename-less part.
- Added multipart-parser regressions for shorthand, metadata, and repeated files; regenerated the preview.

### Ticket 009 — Support synchronous binary upload iterables

- Adapt synchronous binary iterables lazily to async-compatible chunks, preserving bytes and async iterables.
- Upload generator failures retain their cause in `TransportError`.
- Added lazy-consumption and runtime upload regressions for protocol/HTTPX modes and required/optional bodies; regenerated the preview.

### Ticket 008 — Wrap binary stream read failures

- Buffered and streaming binary reads now raise `TransportError`, preserving the original cause and exception chain.
- Consumer exceptions and cancellation remain unchanged; response cleanup still runs.
- Added mid-download failure regressions and regenerated the preview.

### Ticket 007 — Close streaming responses on cancellation

- Put the entire entered response lifetime under unconditional async context cleanup, including validation and error-body reads before yield.
- Preserve cancellation unchanged and keep the borrowed transport open.
- Added cancellation regressions before/after yield that verify response closure exactly once.

### Ticket 006 — Support mixed binary success responses

- Preserve every declared successful representation in buffered and streaming methods, including JSON/text alongside binary content and empty 204 responses.
- Keep exact-status precedence over ranges and incremental binary downloads.
- Added generated-client status/media dispatch regressions and regenerated the preview.

### Ticket 005 — Preserve dot-valued path segments

- Encode standalone dot segments so HTTPX preserves the intended route.
- Added wire-URL regressions for interior/trailing identifiers, buffered/streaming methods, dots, slashes, percent signs, and ordinary values; regenerated the preview.

### Ticket 004 — Avoid operation argument/local collisions

- Disambiguate API parameter and multipart argument names that collide with generated locals or serialization helpers using an `_arg` suffix, preserving wire names.
- Added a real HTTPX regression covering path, header, cookie, query, helper names, and a multipart `files` array.

### Ticket 003 — Distinguish JSON null bodies from omission

- Required and explicit optional root null bodies send literal `null` with the selected JSON Content-Type.
- Optional JSON body arguments use a separate omission sentinel; leaving out the argument sends no body.
- Covered required/optional bodies and JSON media variants with real HTTPX requests; regenerated the preview.

### Ticket 002 — Omit unset defaults from JSON Merge Patch

- Merge patches serialize only explicitly supplied fields, recursively and by alias; explicit default values and null deletion instructions remain present.
- Ordinary JSON requests retain their existing non-null default behavior.
- Added a generated-client regression for explicit defaults and nested aliases.

### Ticket 001 — Preserve explicit JSON null fields

- JSON request serialization preserves explicit nulls, including nested and aliased fields, while omitting unset nullable fields.
- Ordinary request models continue to send non-null schema defaults. JSON Merge Patch default omission is handled separately by ticket 002.
- Added generated-client HTTPX regressions for required/optional bodies and media variants; regenerated the preview.

### Ticket 037 â€” Restore Ruff format checks

- Apply the configured formatter to the four files failing the baseline CI format check, without runtime changes.
- Delivered before the runtime stack so every PR can pass lint and format checks.
- Verified all 134 baseline tests, Ruff lint/format, and unchanged generated preview output.
