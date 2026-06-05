#!/usr/bin/env bash
# Regenerate OpenAPI spec, source index, field lineage, and optional samples.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/fetch_openapi.py
python3 scripts/build_source_index.py
python3 scripts/build_field_lineage.py
if [[ "${1:-}" == "--with-samples" ]]; then
  python3 scripts/sample_responses.py
fi
echo "Done. Run 'mintlify dev' to preview."
