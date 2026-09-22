#!/usr/bin/env bash
# Build one static Mintlify export for dev or main GitHub Pages trees.
set -euo pipefail

VARIANT="${1:?usage: build_static_site.sh dev|main [output_dir]}"
OUT_DIR="${2:-_build/${VARIANT}}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

case "$VARIANT" in
  dev) CONFIG="openapi/config-dev.json" ;;
  main) CONFIG="openapi/config-main.json" ;;
  *)
    echo "unknown variant: $VARIANT (expected dev or main)" >&2
    exit 1
    ;;
esac

SPEC="$(python3 -c "import json; print(json.load(open('$CONFIG'))['openapi_output'])")"
BASE="$(python3 -c "import json; print(json.load(open('$CONFIG'))['pages_base_path'])")"

python3 scripts/prepare_docs_variant.py "$VARIANT"
python3 scripts/fetch_openapi.py --config "$CONFIG" --output "$SPEC"

if [[ "${SKIP_GENERATED:-0}" != "1" ]]; then
  python3 scripts/build_source_index.py
  python3 scripts/build_field_lineage.py
fi

mintlify validate
mintlify export --output "site-${VARIANT}.zip"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
unzip -q "site-${VARIANT}.zip" -d "$OUT_DIR"
cp -R openapi "$OUT_DIR/openapi"
python3 scripts/patch_github_pages_basepath.py "$OUT_DIR" --base-path "$BASE"
rm -rf \
  "$OUT_DIR/scripts" \
  "$OUT_DIR/.gitignore" \
  "$OUT_DIR/.DS_Store" \
  "$OUT_DIR/serve.js" \
  "$OUT_DIR/Start Docs.command" \
  "$OUT_DIR/Start Docs.bat" \
  2>/dev/null || true

echo "Built ${VARIANT} site at ${OUT_DIR} (base path ${BASE})"
