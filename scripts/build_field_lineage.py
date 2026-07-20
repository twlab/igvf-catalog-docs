#!/usr/bin/env python3
"""
Build field-lineage documentation: map portal file columns through KG adapters
to Catalog API fields. Uses adapter source from igvf-catalog repo (GitHub raw)
and generated/source-index.json. Falls back to cached generated/field-lineage/*.json.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

ADAPTERS_BASE = (
    "https://raw.githubusercontent.com/IGVF-DACC/igvf-catalog/dev/data/adapters"
)
FILE_ACC = re.compile(r"\b(?:IGVFFI|ENCFF)[A-Z0-9]+\b")
ADAPTER_LIST_URL = (
    "https://api.github.com/repos/IGVF-DACC/igvf-catalog/contents/data/adapters?ref=dev"
)


def load_source_index(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("accessions") or []


def list_adapter_files() -> list[str]:
    try:
        req = urllib.request.Request(
            ADAPTER_LIST_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "igvf-catalog-docs"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            items = json.loads(resp.read().decode("utf-8"))
        return [
            i["name"]
            for i in items
            if i.get("name", "").endswith("_adapter.py") or i.get("name") == "file_fileset_adapter.py"
        ]
    except Exception as e:
        print(f"Warning: could not list adapters: {e}", file=sys.stderr)
        return ["file_fileset_adapter.py", "AFGR_eqtl_adapter.py", "STARR_seq_adapter.py"]


def fetch_adapter_source(name: str) -> str:
    url = f"{ADAPTERS_BASE}/{name}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_field_mappings(source: str, adapter_name: str) -> list[dict[str, str]]:
    """Heuristic: find dict literals with string keys that look like KG/API fields."""
    mappings: list[dict[str, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return mappings

    kg_keys = {
        "log10pvalue", "effect_size", "p_value", "files_fileset", "method", "label",
        "source", "name", "biological_context", "biosample_term", "class",
        "variant_id", "gene_id", "score", "r2", "d_prime",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if not isinstance(k, ast.Constant) or not isinstance(k.value, str):
                    continue
                key = k.value
                if key not in kg_keys:
                    continue
                src = ""
                if isinstance(v, ast.Name):
                    src = v.id
                elif isinstance(v, ast.Constant):
                    src = repr(v.value)
                elif isinstance(v, ast.Subscript) and isinstance(v.value, ast.Name):
                    src = f"{v.value.id}[...]"
                mappings.append(
                    {
                        "adapter": adapter_name,
                        "arango_or_api_field": str(key),
                        "adapter_expression": src or "(computed)",
                        "portal_column": "",
                        "notes": "",
                    }
                )
    # dedupe
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for m in mappings:
        t = (m["adapter"], m["arango_or_api_field"])
        if t in seen:
            continue
        seen.add(t)
        out.append(m)
    return out[:80]


def build_adapter_index(adapter_names: list[str]) -> dict[str, Any]:
    index: dict[str, Any] = {"adapters": {}, "file_mentions": {}}
    for name in adapter_names:
        try:
            src = fetch_adapter_source(name)
        except Exception as e:
            print(f"Skip {name}: {e}", file=sys.stderr)
            continue
        index["adapters"][name] = {
            "mappings": extract_field_mappings(src, name),
            "mentioned_files": sorted(set(FILE_ACC.findall(src))),
        }
        for acc in index["adapters"][name]["mentioned_files"]:
            index["file_mentions"].setdefault(acc, []).append(name)
    return index


def write_lineage_mdx(index: dict[str, Any], source_entries: list[dict[str, Any]], out: Path) -> None:
    by_acc = {e["accession"]: e for e in source_entries if e.get("accession")}

    lines = [
        "---",
        "title: 'Field Lineage'",
        "description: 'Portal file columns through adapters to Catalog API fields'",
        "icon: 'arrow-right-arrow-left'",
        "---",
        "",
        "# Field Lineage",
        "",
        "This page documents how fields flow from **portal files** (with "
        "[file format specifications](https://data.igvf.org)) through "
        "[KG loading adapters](https://github.com/IGVF-DACC/igvf-catalog/tree/dev/data/adapters) "
        "into **ArangoDB** and the **REST API**.",
        "",
        "For automated deep traces, use the `trace` tool in "
        "[igvf-catalog-dev-agents](https://github.com/IGVF/igvf-catalog-dev-agents).",
        "",
    ]

    adapters = index.get("adapters") or {}
    if not adapters:
        lines.append("_Run `python3 scripts/build_field_lineage.py` to populate adapter mappings._")
    else:
        for adapter_name, info in sorted(adapters.items()):
            lines.extend([
                f"## {adapter_name}",
                "",
            ])
            mentioned = info.get("mentioned_files") or []
            if mentioned:
                file_links = []
                for acc in mentioned[:12]:
                    ent = by_acc.get(acc, {})
                    link = ent.get("portal_link") or f"https://encodeproject.org/{acc}/"
                    file_links.append(f"[{acc}]({link})")
                lines.append("**Referenced files:** " + ", ".join(file_links))
                lines.append("")

            mappings = info.get("mappings") or []
            if mappings:
                lines.extend([
                    "| Arango / API field | Adapter expression | Notes |",
                    "|--------------------|--------------------|-------|",
                ])
                for m in mappings[:25]:
                    field = m["arango_or_api_field"]
                    expr = m["adapter_expression"].replace("|", "\\|")
                    lines.append(f"| `{field}` | `{expr}` | |")
                lines.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-index", default="generated/source-index.json")
    ap.add_argument("--json-out", default="generated/field-lineage/index.json")
    ap.add_argument("--mdx-out", default="data-sources/field-lineage/index.mdx")
    ap.add_argument("--cache-only", action="store_true")
    args = ap.parse_args()

    source_entries = load_source_index(Path(args.source_index))
    json_out = Path(args.json_out)

    if args.cache_only and json_out.exists():
        index = json.loads(json_out.read_text(encoding="utf-8"))
    else:
        names = list_adapter_files()
        print(f"Fetching {len(names)} adapters", file=sys.stderr)
        index = build_adapter_index(names)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    write_lineage_mdx(index, source_entries, Path(args.mdx_out))
    print(f"Wrote {json_out} and {args.mdx_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
