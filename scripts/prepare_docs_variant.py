#!/usr/bin/env python3
"""Prepare docs.json and API intro for a dev or main GitHub Pages variant."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VARIANT_CONFIG = {
    "dev": ROOT / "openapi" / "config-dev.json",
    "main": ROOT / "openapi" / "config-main.json",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_api_intro(cfg: dict) -> str:
    api_base = cfg["api_base_url"]
    swagger_ui = cfg["swagger_ui_url"].rstrip("/")
    label = cfg["label"]
    banner = cfg["banner"]
    return f"""---
title: 'API Introduction'
description: 'IGVF Catalog REST API — {label.lower()} environment'
icon: 'code'
---

<Warning>
{banner} Base URL: `{api_base}`.
</Warning>

# IGVF Catalog REST API

The IGVF Catalog exposes an OpenAPI-compliant REST API for querying the genomics knowledge graph: variants, genes, proteins, regulatory elements, QTLs, pathways, drugs, and more.

## Base URL

```
{api_base}
```

Interactive Swagger UI: [{swagger_ui.replace("https://", "")}]({swagger_ui}/)

## Pagination

- **`page`** — 0-based page index (default `0`)
- **`limit`** — page size; maximum **500** on most endpoints

Example: `GET /variants?region=chr1:1157520-1158189&page=0`

## Coordinates

The database uses **0-based, half-open** genomic coordinates on **GRCh38** (human) and **GRCm39** (mouse).

## Query patterns

Most endpoints accept **one primary filter** plus optional refinements. Examples in each endpoint description are tested individually (see [audit results](https://github.com/IGVF-DACC/igvf-catalog-docs/tree/main/scripts)).

### Variant identifiers

Variants can be queried by any of:

| Parameter | Example |
|-----------|---------|
| `variant_id` / `spdi` | `NC_000020.11:3658947:A:G` |
| `hgvs` | `NC_000020.11:g.3658948A>G` |
| `rsid` | `rs58658771` |
| `ca_id` | `CA739473472` |
| `region` | `chr1:1157520-1158189` (max 10 kb) |

### Dataset provenance (`files_fileset`)

Many edges are tagged with a **`files_fileset`** accession (e.g. `IGVFFI9602ILPC`, `ENCFF968BZL`) linking Catalog results to source files on the [IGVF Portal](https://data.igvf.org) or [ENCODE Portal](https://encodeproject.org). See [Data Sources](/data-sources/index) and [Field lineage](/data-sources/field-lineage/index) for file metadata and column-to-API field mappings.

## Related resources

- [IGVF Catalog MCP](https://github.com/IGVF-DACC/igvf-catalog-mcp) — higher-level graph queries for agents
- [Live Catalog UI](https://catalog.igvf.org)
"""


def prepare_variant(variant: str) -> dict:
    config_path = VARIANT_CONFIG[variant]
    cfg = _load_json(config_path)
    openapi_spec = cfg["openapi_output"]

    docs_path = ROOT / "docs.json"
    docs = _load_json(docs_path)
    docs = deepcopy(docs)
    docs["name"] = cfg.get("site_name", docs.get("name", "IGVF Catalog"))
    docs["api"]["openapi"] = openapi_spec
    for tab in docs.get("navigation", {}).get("tabs", []):
        if tab.get("openapi"):
            tab["openapi"] = openapi_spec

    docs_path.write_text(json.dumps(docs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    intro_path = ROOT / "api-reference" / "introduction.mdx"
    intro_path.write_text(render_api_intro(cfg), encoding="utf-8")

    return cfg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=sorted(VARIANT_CONFIG))
    args = parser.parse_args()

    cfg = prepare_variant(args.variant)
    print(
        f"Prepared {args.variant} docs: openapi={cfg['openapi_output']}, "
        f"base={cfg['pages_base_path']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
