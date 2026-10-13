# Changelog

## Unreleased

### Ticket 001 â€” Preserve explicit JSON null fields

- JSON request serialization preserves explicit nulls, including nested and aliased fields, while omitting unset nullable fields.
- Ordinary request models continue to send non-null schema defaults. JSON Merge Patch default omission is handled separately by ticket 002.
- Added generated-client HTTPX regressions for required/optional bodies and media variants; regenerated the preview.

### Ticket 037 â€” Restore Ruff format checks

- Apply the configured formatter to the four files failing the baseline CI format check, without runtime changes.
- Delivered before the runtime stack so every PR can pass lint and format checks.
- Verified all 134 baseline tests, Ruff lint/format, and unchanged generated preview output.
