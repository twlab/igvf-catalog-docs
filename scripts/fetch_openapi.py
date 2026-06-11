#!/usr/bin/env python3
"""Download OpenAPI spec from Catalog Swagger UI and write openapi/catalog-dev.openapi.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from openapi_utils import load_config, load_spec_from_swagger_init, normalize_openapi_spec  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="openapi/config.json")
    ap.add_argument("--output", default="openapi/catalog-dev.openapi.json")
    args = ap.parse_args()

    cfg = load_config(args.config)
    url = cfg["swagger_init_url"]
    spec = load_spec_from_swagger_init(url)
    spec = normalize_openapi_spec(spec)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
        f.write("\n")

    paths = len(spec.get("paths") or {})
    print(f"Fetched OpenAPI from {url}", file=sys.stderr)
    print(f"Wrote {out} ({paths} paths)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
