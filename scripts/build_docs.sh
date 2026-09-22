#!/usr/bin/env bash
# Regenerate OpenAPI spec, source index, field lineage, and optional samples.
set -euo pipefail
cd "$(dirname "$0")/.."
VARIANT="${1:-dev}"
python3 scripts/prepare_docs_variant.py "$VARIANT"
OUTPUT="$(python3 -c "import json; print(json.load(open('openapi/config-${VARIANT}.json'))['openapi_output'])")"
python3 scripts/fetch_openapi.py --config "openapi/config-${VARIANT}.json" --output "$OUTPUT"
python3 scripts/build_source_index.py
python3 scripts/build_field_lineage.py
if [[ "${2:-}" == "--with-samples" ]]; then
  python3 scripts/sample_responses.py
fi
echo "Done. Run 'mintlify dev' to preview (requires docs.json)."
