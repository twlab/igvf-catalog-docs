#!/usr/bin/env python3
"""
For each GET operation, call the dev API with one documented example (+ page=0)
and store the first result JSON under openapi/examples/{operationId}.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from openapi_utils import load_config, load_spec_from_swagger_init  # noqa: E402

# Reuse audit helpers
from catalog_per_example_audit import (  # noqa: E402
    clean_param_value,
    extract_kv_ordered,
    rows_for_get,
)


def fetch_json(url: str, timeout: float) -> Any | None:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        return None


def first_item(data: Any) -> Any:
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v:
                return v[0]
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="openapi/config.json")
    ap.add_argument("--out-dir", default="openapi/examples")
    ap.add_argument("--timeout", type=float, default=35.0)
    args = ap.parse_args()

    cfg = load_config(args.config)
    spec = load_spec_from_swagger_init(cfg["swagger_init_url"])
    base = spec["servers"][0]["url"].rstrip("/")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    for path, path_item in sorted(spec["paths"].items()):
        for method, op in path_item.items():
            if method.upper() != "GET":
                continue
            if not isinstance(op, dict):
                continue
            oid = op.get("operationId") or re.sub(r"[^\w]", "_", path.strip("/"))
            rows = rows_for_get(path, op, base)
            url = next((r["url"] for r in rows if r.get("url")), None)
            if not url:
                continue
            data = fetch_json(url, args.timeout)
            if data is None:
                continue
            sample = first_item(data)
            safe = re.sub(r"[^\w.-]", "_", oid)[:120]
            out = out_dir / f"{safe}.json"
            with out.open("w", encoding="utf-8") as f:
                json.dump({"url": url, "sample": sample}, f, indent=2)
                f.write("\n")
            saved += 1

    print(f"Saved {saved} examples to {out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
