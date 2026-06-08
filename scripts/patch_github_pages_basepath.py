#!/usr/bin/env python3
"""Patch Mintlify static export for GitHub Pages project-site subpaths.

Mintlify export emits root-absolute asset URLs (e.g. /_next/static/...).
On https://<org>.github.io/<repo>/ those assets 404 unless prefixed with the
repository name. This script rewrites HTML/JS/CSS after `mintlify export`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TEXT_EXTENSIONS = {".html", ".js", ".css", ".json", ".xml", ".txt"}

# Mintlify router base path variable in prerendered HTML.
ROUTER_BASE_RE = re.compile(r'var b=""')

# href="/...", src="/...", etc. — skip protocol-relative and external URLs.
ATTR_RE = re.compile(
    r'\b(href|src|action)=(["\'])(/[^"\']*)\2',
    re.IGNORECASE,
)


def patch_content(content: str, base_path: str) -> str:
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    base_path = base_path.rstrip("/")

    content = ROUTER_BASE_RE.sub(f'var b="{base_path}"', content, count=1)

    def repl_attr(match: re.Match[str]) -> str:
        attr, quote, path = match.group(1), match.group(2), match.group(3)
        if path.startswith("//"):
            return match.group(0)
        if path.startswith(base_path + "/") or path == base_path:
            return match.group(0)
        return f"{attr}={quote}{base_path}{path}{quote}"

    content = ATTR_RE.sub(repl_attr, content)

    # Catch quoted root paths in bundled JS/CSS (chunk loaders, preload URLs).
    for prefix in (
        "/_next/",
        "/images/",
        "/favicons/",
        "/custom.css",
        "/llms.txt",
        "/sitemap.xml",
        "/openapi/",
    ):
        quoted = f'"{prefix}'
        replacement = f'"{base_path}{prefix}'
        if quoted in content:
            content = content.replace(quoted, replacement)
        single = f"'{prefix}"
        replacement_single = f"'{base_path}{prefix}"
        if single in content:
            content = content.replace(single, replacement_single)

    return content


def patch_tree(root: Path, base_path: str) -> int:
    changed = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        original = path.read_text(encoding="utf-8")
        updated = patch_content(original, base_path)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "site_dir",
        type=Path,
        help="Unzipped Mintlify export directory",
    )
    parser.add_argument(
        "--base-path",
        default="/igvf-catalog-docs",
        help="GitHub Pages project-site base path (default: /igvf-catalog-docs)",
    )
    args = parser.parse_args()

    if not args.site_dir.is_dir():
        print(f"error: site directory not found: {args.site_dir}", file=sys.stderr)
        return 1

    changed = patch_tree(args.site_dir, args.base_path)
    print(f"Patched {changed} file(s) with base path {args.base_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
