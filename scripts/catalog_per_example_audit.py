#!/usr/bin/env python3
"""
For each GET in the IGVF Catalog Swagger OpenAPI spec, call the API once per
documented query example (param=value) in isolation: only that query param
plus page=0 when the operation defines page. No other optional params are
combined.

Path templates are invoked once per operation using all path placeholders
filled from the same description (path cannot be partially requested).

Output: TSV with endpoint, operation_id, param=value tested, HTTP status,
n_results (top-level list length, else first JSON array value length, else empty).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

SWAGGER_INIT_DEFAULT = (
    "https://catalog-api-dev.demo.igvf.org/swagger-ui-init.js"
)

try:
    from openapi_utils import load_spec_from_swagger_init as load_spec
except ImportError:
    def load_spec(swagger_init_url: str) -> dict[str, Any]:
        text = urllib.request.urlopen(swagger_init_url, timeout=120).read().decode("utf-8")
        key = '"swaggerDoc":'
        i = text.find(key)
        if i < 0:
            raise RuntimeError("swaggerDoc not found")
        i += len(key)
        while i < len(text) and text[i] in " \n\t":
            i += 1
        if text[i] != "{":
            raise RuntimeError("expected { after swaggerDoc")
        depth = 0
        start = i
        for j in range(i, len(text)):
            c = text[j]
            if c == '"':
                j += 1
                while j < len(text):
                    if text[j] == "\\":
                        j += 2
                        continue
                    if text[j] == '"':
                        break
                    j += 1
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : j + 1])
        raise RuntimeError("unclosed swaggerDoc JSON")


def strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return s


def extract_kv_ordered(desc: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    text = strip_html(desc or "")
    for m in re.finditer(r"([\w_]+)\s*=\s*([^,\n]+)", text):
        k, v = m.group(1), m.group(2).strip().rstrip(" .")
        if len(k) > 1 and k.lower() != "example":
            out.append((k, v))
    return out


def clean_param_value(name: str, v: str) -> str:
    v = (v or "").strip()
    if not v:
        return v
    if name == "verbose":
        return "true" if "true" in v.lower() else "false"
    v = re.split(r"\s*\(maximum\b", v, maxsplit=1, flags=re.I)[0].strip()
    if " or " in v and name in ("protein_id", "protein_name"):
        for part in v.split(" or "):
            p2 = part.split(" (")[0].strip()
            m = re.match(r"^ENSP[\d.]+", p2)
            if m:
                return m.group(0)
        v = v.split(" or ")[0].split(" (")[0].strip()
    elif " (" in v and not v.startswith("("):
        head = v.split(" (", 1)[0].strip()
        if re.match(r"^[\w.\-:!]+$", head) or re.match(r"^rs", head, re.I) or re.match(r"^PA\d+$", head):
            v = head
    v = re.split(r"\s*\(only\b", v, maxsplit=1, flags=re.I)[0].strip()
    if name == "organism" and " or " in v:
        v = v.split(" or ")[0].strip()
    if name == "GENCODE_category" and " or " in v.lower():
        v = "coding"
    if name in ("gene_id", "transcript_id", "drug_id") and " (" in v:
        v = v.split(" (")[0].strip()
    if name == "entrez" and ":" in v:
        v = v.split(":")[-1].strip()
    return v.strip()


def count_results(data: Any) -> tuple[int | None, str]:
    if isinstance(data, list):
        return len(data), "list"
    if isinstance(data, dict):
        for _k, v in data.items():
            if isinstance(v, list):
                return len(v), f"object[{_k}]"
        return None, "object"
    return None, type(data).__name__


def build_path(path: str, op: dict[str, Any], raw_ordered: list[tuple[str, str]]) -> tuple[str | None, str]:
    path_param_names = {p["name"] for p in op.get("parameters") or [] if p.get("in") == "path"}
    raw = dict(raw_ordered)
    out = path
    missing: list[str] = []
    for name in sorted(path_param_names):
        if name not in raw:
            missing.append(name)
            continue
        out = out.replace("{" + name + "}", urllib.parse.quote(clean_param_value(name, raw[name]), safe=""))
    if missing:
        return None, "missing_path_example:" + ",".join(missing)
    if "{" in out:
        return None, "unfilled_path_template"
    return out, ""


def rows_for_get(path: str, op: dict[str, Any], base: str) -> list[dict[str, Any]]:
    oid = op.get("operationId", "")
    if oid == "query.health":
        return []

    ordered = extract_kv_ordered(op.get("description") or "")
    params = op.get("parameters") or []
    qnames = {p["name"] for p in params if p.get("in") == "query"}
    has_page = "page" in qnames

    ppath, perr = build_path(path, op, ordered)
    if ppath is None:
        return [
            {
                "endpoint": path,
                "operation_id": oid,
                "param_value_tested": "(path)",
                "http_status": "",
                "n_results": "",
                "result_shape": "",
                "notes": perr,
                "url": "",
            }
        ]

    rows: list[dict[str, Any]] = []
    seen_query_keys: set[str] = set()
    for k, v in ordered:
        if k not in qnames:
            continue
        if k in seen_query_keys:
            continue
        seen_query_keys.add(k)
        cv = clean_param_value(k, v)
        if not cv:
            continue
        q: dict[str, str] = {k: cv}
        if has_page:
            q["page"] = "0"
        url = base + "/" + ppath.lstrip("/") + "?" + urllib.parse.urlencode(q)
        rows.append(
            {
                "endpoint": path,
                "operation_id": oid,
                "param_value_tested": f"{k}={cv}",
                "http_status": "",
                "n_results": "",
                "result_shape": "",
                "notes": "",
                "url": url,
            }
        )

    if not rows and not qnames:
        q: dict[str, str] = {}
        if has_page:
            q["page"] = "0"
        url = base + "/" + ppath.lstrip("/") + ("?" + urllib.parse.urlencode(q) if q else "")
        rows.append(
            {
                "endpoint": path,
                "operation_id": oid,
                "param_value_tested": "(no query examples in description)",
                "http_status": "",
                "n_results": "",
                "result_shape": "",
                "notes": "",
                "url": url,
            }
        )

    return rows


def fetch_row(row: dict[str, Any], timeout: float) -> dict[str, Any]:
    url = row["url"]
    if not url:
        return row
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        row["http_status"] = str(e.code)
        row["notes"] = (e.reason or "")[:200]
        return row
    except Exception as e:
        row["http_status"] = ""
        row["notes"] = str(e)[:200]
        return row

    row["http_status"] = str(status)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        row["notes"] = "invalid_json"
        return row

    n, shape = count_results(data)
    row["n_results"] = "" if n is None else str(n)
    row["result_shape"] = shape
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swagger-init", default=SWAGGER_INIT_DEFAULT)
    ap.add_argument("--output", default="scripts/catalog_per_example_audit_results.tsv")
    ap.add_argument("--timeout", type=float, default=35.0)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    spec = load_spec(args.swagger_init)
    base = spec["servers"][0]["url"].rstrip("/")

    all_rows: list[dict[str, Any]] = []
    for path, path_item in sorted(spec["paths"].items()):
        for method, op in path_item.items():
            if method.upper() != "GET":
                continue
            if not isinstance(op, dict):
                continue
            all_rows.extend(rows_for_get(path, op, base))

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(fetch_row, r, args.timeout) for r in all_rows if r.get("url")]
        for f in as_completed(futs):
            f.result()

    fieldnames = [
        "endpoint",
        "operation_id",
        "param_value_tested",
        "http_status",
        "n_results",
        "result_shape",
        "notes",
        "url",
    ]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in all_rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    print(f"Wrote {len(all_rows)} rows to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
