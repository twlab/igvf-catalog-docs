#!/usr/bin/env python3
"""
Scan docs and audit data for IGVFF*/ENCFF* accessions; resolve portal metadata
including file_format_specification; write generated/source-index.json and
data-sources/index.mdx.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

IGVF_FILE = re.compile(r"\bIGVFFI[A-Z0-9]+\b")
ENCODE_FILE = re.compile(r"\bENCFF[A-Z0-9]+\b")
IGVF_FILESET = re.compile(r"\bIGVFDS[A-Z0-9]+\b")
ENCODE_FILESET = re.compile(r"\bENCSR[A-Z0-9]+\b")


def collect_accessions(root: Path) -> set[str]:
    found: set[str] = set()
    patterns = (IGVF_FILE, ENCODE_FILE, IGVF_FILESET, ENCODE_FILESET)
    for path in root.rglob("*"):
        if path.suffix not in (".mdx", ".md", ".tsv", ".json", ".py"):
            continue
        if "audit_snapshots" in path.parts or "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in patterns:
            found.update(pat.findall(text))
    return found


def portal_kind(accession: str) -> str:
    if accession.startswith("IGVF"):
        return "igvf"
    return "encode"


def fetch_portal_json(accession: str, timeout: float = 30) -> dict[str, Any] | None:
    kind = portal_kind(accession)
    if kind == "igvf":
        url = f"https://data.igvf.org/{accession}?format=json"
    else:
        url = f"https://www.encodeproject.org/{accession}/?format=json"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "igvf-catalog-docs/1.0 (documentation build)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def link_for(accession: str) -> str:
    if accession.startswith("IGVF"):
        return f"https://data.igvf.org/{accession}"
    return f"https://www.encodeproject.org/{accession}/"


def extract_format_spec(obj: dict[str, Any]) -> dict[str, str]:
    spec = obj.get("file_format_specification")
    if not spec:
        return {}
    if isinstance(spec, str):
        return {"@id": spec, "accession": spec.rstrip("/").split("/")[-1]}
    if isinstance(spec, dict):
        acc = spec.get("accession") or (spec.get("@id") or "").rstrip("/").split("/")[-1]
        return {"@id": spec.get("@id", ""), "accession": acc, "title": spec.get("title", "")}
    return {}


def summarize(obj: dict[str, Any], accession: str) -> dict[str, Any]:
    fmt_spec = extract_format_spec(obj)
    fmt_spec_link = ""
    if fmt_spec.get("accession"):
        base = "https://data.igvf.org" if accession.startswith("IGVF") else "https://www.encodeproject.org"
        fmt_spec_link = f"{base}/{fmt_spec['accession']}/"
    lab = obj.get("lab") or {}
    lab_title = lab.get("title", "") if isinstance(lab, dict) else str(lab)
    assay = obj.get("assay_title") or obj.get("preferred_assay_title") or ""
    if isinstance(assay, list):
        assay = ", ".join(str(x) for x in assay)
    return {
        "accession": accession,
        "portal": portal_kind(accession),
        "portal_link": link_for(accession),
        "title": obj.get("title") or obj.get("accession") or accession,
        "file_format": obj.get("file_format", ""),
        "output_type": obj.get("output_type", ""),
        "assay_title": assay,
        "status": obj.get("status", ""),
        "lab": lab_title,
        "file_format_specification": fmt_spec.get("accession", ""),
        "file_format_specification_link": fmt_spec_link,
        "schema_version": obj.get("schema_version", ""),
    }


def resolve_one(accession: str, timeout: float) -> dict[str, Any]:
    obj = fetch_portal_json(accession, timeout)
    if obj is None:
        return {
            "accession": accession,
            "portal": portal_kind(accession),
            "portal_link": link_for(accession),
            "error": "fetch_failed",
        }
    return summarize(obj, accession)


def write_index_mdx(entries: list[dict[str, Any]], out_path: Path, cfg: dict[str, Any]) -> None:
    files = [e for e in entries if e["accession"].startswith(("IGVFF", "ENCFF"))]
    files.sort(key=lambda x: x["accession"])

    lines = [
        "---",
        "title: 'Data Sources Index'",
        "description: 'IGVF and ENCODE portal files referenced by the Catalog'",
        "icon: 'database'",
        "---",
        "",
        "<Warning>",
        cfg.get("banner", ""),
        "</Warning>",
        "",
        "# Data Sources Index",
        "",
        "Catalog edges often reference source files via **`files_fileset`**. "
        "Each file below links to its portal record and **file format specification** "
        "(column definitions for the raw file).",
        "",
        "See also [Files & Filesets](/data-sources/files-filesets) and [Field lineage](/data-sources/field-lineage/index).",
        "",
        "| File | Portal | Format | Format spec | Assay | Lab | Status |",
        "|------|--------|--------|-------------|-------|-----|--------|",
    ]
    for e in files:
        acc = e["accession"]
        portal = f"[{acc}]({e.get('portal_link', '#')})"
        fmt = e.get("file_format", "") or "—"
        spec_acc = e.get("file_format_specification", "")
        spec_link = e.get("file_format_specification_link", "")
        spec_cell = f"[{spec_acc}]({spec_link})" if spec_acc and spec_link else (spec_acc or "—")
        assay = (e.get("assay_title") or "—").replace("|", "\\|")[:40]
        lab = (e.get("lab") or "—").replace("|", "\\|")[:30]
        status = e.get("status") or "—"
        lines.append(f"| {portal} | {e.get('portal', '')} | {fmt} | {spec_cell} | {assay} | {lab} | {status} |")

    if not files:
        lines.append("| _No file accessions resolved yet — run `python3 scripts/build_source_index.py`_ | | | | | | |")

    lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json-out", default="generated/source-index.json")
    ap.add_argument("--mdx-out", default="data-sources/index.mdx")
    ap.add_argument("--config", default="openapi/config.json")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max", type=int, default=0, help="Max accessions to resolve (0=all)")
    args = ap.parse_args()

    root = Path(args.root)
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    accessions = sorted(collect_accessions(root))
    if args.max:
        accessions = accessions[: args.max]

    print(f"Found {len(accessions)} accessions", file=sys.stderr)
    entries: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(resolve_one, a, args.timeout): a for a in accessions}
        for fut in as_completed(futs):
            entries.append(fut.result())

    entries.sort(key=lambda x: x["accession"])
    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    with json_out.open("w", encoding="utf-8") as f:
        json.dump({"accessions": entries, "count": len(entries)}, f, indent=2)
        f.write("\n")

    write_index_mdx(entries, Path(args.mdx_out), cfg)
    print(f"Wrote {json_out} and {args.mdx_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
