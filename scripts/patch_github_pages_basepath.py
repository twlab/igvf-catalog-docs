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
HEAD_INJECT_MARKER = "data-igvf-static-export"

# Inline script: GitHub Pages has no Next.js/RSC server; force full page loads.
STATIC_HOSTING_SCRIPT = """<script data-igvf-static-export="1">(function(){var B="/__BASE_PATH__";document.addEventListener("click",function(e){var a=e.target&&e.target.closest&&e.target.closest("a[href]");if(!a||e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||a.hasAttribute("download"))return;var tgt=a.getAttribute("target");if(tgt&&tgt!=="_self")return;var href=a.getAttribute("href");if(!href||href.charAt(0)==="#"||/^(mailto:|tel:|javascript:)/i.test(href))return;var u;try{u=new URL(href,location.href)}catch(_){return}if(u.origin!==location.origin)return;if(u.pathname===B||u.pathname.indexOf(B+"/")===0){e.preventDefault();e.stopImmediatePropagation();location.assign(u.href)}},true);if(window.fetch){var nf=window.fetch.bind(window);window.fetch=function(input,init){init=init||{};var headers=init.headers,isRsc=false;function gh(n){if(!headers)return null;if(typeof Headers!=="undefined"&&headers instanceof Headers)return headers.get(n);if(Array.isArray(headers)){for(var i=0;i<headers.length;i++)if(headers[i]&&headers[i][0].toLowerCase()===n.toLowerCase())return headers[i][1]}else if(typeof headers==="object"){for(var k in headers)if(k.toLowerCase()===n.toLowerCase())return headers[k]}return null}if(gh("RSC")==="1"||gh("rsc")==="1")isRsc=true;var acc=gh("Accept")||"";if(acc.indexOf("text/x-component")!==-1)isRsc=true;if(isRsc)return Promise.reject(new Error("RSC disabled on static GitHub Pages export"));return nf(input,init)}}})();</script>"""

# Mintlify inline router base path variable in prerendered HTML.
ROUTER_BASE_RE = re.compile(r'var b=""')

# href="/...", src="/...", etc. — skip protocol-relative and external URLs.
ATTR_RE = re.compile(
    r'\b(href|src|action)=(["\'])(/[^"\']*)\2',
    re.IGNORECASE,
)

# Root-absolute internal paths embedded in JSON/RSC payloads and bundled JS.
INTERNAL_PREFIXES = (
    "/_next/",
    "/_mintlify/",
    "/api-reference/",
    "/data-sources/",
    "/nodes/",
    "/region/",
    "/introduction",
    "/using-search",
    "/openapi/",
    "/images/",
    "/favicons/",
    "/custom.css",
    "/llms.txt",
    "/sitemap.xml",
)


def _prefixed(base_path: str, path: str) -> bool:
    return path == base_path or path.startswith(base_path + "/")


def _quote_replace(content: str, quote: str, prefix: str, base_path: str) -> str:
    token = f"{quote}{prefix}"
    replacement = f"{quote}{base_path}{prefix}"
    if token not in content:
        return content
    parts: list[str] = []
    start = 0
    while True:
        idx = content.find(token, start)
        if idx == -1:
            parts.append(content[start:])
            break
        before = content[max(0, idx - len(base_path)) : idx]
        if before.endswith(base_path):
            parts.append(content[start : idx + len(token)])
        else:
            parts.append(content[start:idx])
            parts.append(replacement)
        start = idx + len(token)
    return "".join(parts)


def patch_content(content: str, base_path: str) -> str:
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    base_path = base_path.rstrip("/")

    content = ROUTER_BASE_RE.sub(f'var b="{base_path}"', content, count=1)

    def repl_attr(match: re.Match[str]) -> str:
        attr, quote, path = match.group(1), match.group(2), match.group(3)
        if path.startswith("//"):
            return match.group(0)
        if _prefixed(base_path, path):
            return match.group(0)
        return f"{attr}={quote}{base_path}{path}{quote}"

    content = ATTR_RE.sub(repl_attr, content)

    for prefix in INTERNAL_PREFIXES:
        content = _quote_replace(content, '"', prefix, base_path)
        content = _quote_replace(content, "'", prefix, base_path)

    return content


def inject_static_hosting_script(content: str, base_path: str) -> str:
    if HEAD_INJECT_MARKER in content:
        return content
    script = STATIC_HOSTING_SCRIPT.replace("/__BASE_PATH__", base_path)
    head_match = re.search(r"<head[^>]*>", content, re.IGNORECASE)
    if not head_match:
        return content
    insert_at = head_match.end()
    return content[:insert_at] + script + content[insert_at:]


def patch_html(content: str, base_path: str) -> str:
    content = patch_content(content, base_path)
    return inject_static_hosting_script(content, base_path)


def patch_tree(root: Path, base_path: str) -> int:
    changed = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        original = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".html":
            updated = patch_html(original, base_path)
        else:
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
