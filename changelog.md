# Changelog

## Unreleased

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
