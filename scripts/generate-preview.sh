#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

uv run httpxgen specs/api.yml preview \
  --package-name preview \
  --tag payments \
  --tag invoices
