#!/usr/bin/env python3
"""Patch Mintlify static export for GitHub Pages project-site subpaths.

Mintlify export emits root-absolute asset URLs (e.g. /_next/static/...).
On https://<org>.github.io/<repo>/ those assets 404 unless prefixed with the
repository name.

Important: do not blindly rewrite quoted paths inside HTML — Next.js embeds the
full navigation tree in RSC flight payloads. Prefixes like "/introduction"
partially match "/api-reference/introduction" and corrupt hydration.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TEXT_EXTENSIONS = {".html", ".js", ".css", ".json", ".xml", ".txt"}
HEAD_INJECT_MARKER = "data-igvf-static-export"

# Force full page loads on static GitHub Pages (no RSC server).
STATIC_HOSTING_SCRIPT = """<script data-igvf-static-export="1">(function(){var B="/__BASE_PATH__";document.addEventListener("click",function(e){var a=e.target&&e.target.closest&&e.target.closest("a[href]");if(!a||e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||a.hasAttribute("download"))return;var tgt=a.getAttribute("target");if(tgt&&tgt!=="_self")return;var href=a.getAttribute("href");if(!href||href.charAt(0)==="#"||/^(mailto:|tel:|javascript:)/i.test(href))return;var u;try{u=new URL(href,location.href)}catch(_){return}if(u.origin!==location.origin)return;if(u.pathname===B||u.pathname.indexOf(B+"/")===0){e.preventDefault();e.stopImmediatePropagation();location.assign(u.href)}},true)})();</script>"""

ROUTER_BASE_RE = re.compile(r'var b=""')

ATTR_RE = re.compile(
    r'\b(href|src|action)=(["\'])(/[^"\']*)\2',
    re.IGNORECASE,
)

# Safe to rewrite globally in bundled JS (not inside partial path segments).
JS_PREFIXES = (
    "/_next/",
    "/_mintlify/",
    "/openapi/",
)


def _normalize_base_path(base_path: str) -> str:
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    return base_path.rstrip("/")


def _prefixed(base_path: str, path: str) -> bool:
    return path == base_path or path.startswith(base_path + "/")


def _quote_replace(content: str, quote: str, prefix: str, base_path: str) -> str:
    escaped_base = re.escape(base_path)
    escaped_prefix = re.escape(prefix)
    pattern = re.compile(rf"{re.escape(quote)}(?!{escaped_base}){escaped_prefix}")
    return pattern.sub(rf"{quote}{base_path}{prefix}", content)


def _patch_attrs(content: str, base_path: str) -> str:
    def repl_attr(match: re.Match[str]) -> str:
        attr, quote, path = match.group(1), match.group(2), match.group(3)
        if path.startswith("//"):
            return match.group(0)
        if _prefixed(base_path, path):
            return match.group(0)
        return f"{attr}={quote}{base_path}{path}{quote}"

    return ATTR_RE.sub(repl_attr, content)


def _patch_quoted_prefixes(content: str, base_path: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        content = _quote_replace(content, '"', prefix, base_path)
        content = _quote_replace(content, "'", prefix, base_path)
    return content


def patch_js(content: str, base_path: str) -> str:
    base_path = _normalize_base_path(base_path)
    return _patch_quoted_prefixes(content, base_path, JS_PREFIXES)


def patch_html(content: str, base_path: str) -> str:
    base_path = _normalize_base_path(base_path)

    content = ROUTER_BASE_RE.sub(f'var b="{base_path}"', content, count=1)
    content = _patch_attrs(content, base_path)
    # Only rewrite JS chunk URLs inside inline RSC payloads — not nav href strings.
    content = content.replace('"/_next/', f'"{base_path}/_next/')
    content = content.replace('\\"/_next/', f'\\"{base_path}/_next/')
    return inject_static_hosting_script(content, base_path)


def inject_static_hosting_script(content: str, base_path: str) -> str:
    if HEAD_INJECT_MARKER in content:
        return content
    script = STATIC_HOSTING_SCRIPT.replace("/__BASE_PATH__", base_path)
    head_match = re.search(r"<head[^>]*>", content, re.IGNORECASE)
    if not head_match:
        return content
    insert_at = head_match.end()
    return content[:insert_at] + script + content[insert_at:]


def patch_tree(root: Path, base_path: str) -> int:
    changed = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        original = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".html":
            updated = patch_html(original, base_path)
        else:
            updated = patch_js(original, base_path)
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
