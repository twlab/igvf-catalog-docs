#!/usr/bin/env python3
"""Patch Mintlify static export for GitHub Pages project-site subpaths.

Mintlify export emits root-absolute asset URLs (e.g. /_next/static/...).
On https://<org>.github.io/<repo>/ those assets 404 unless prefixed with the
repository name.

Important: do not prefix nav ``href`` strings inside RSC flight payloads — the
Next.js client router compares those paths against ``currentPath`` (without the
base path). Prefix only HTML attributes and asset URLs. Also patch every
embedded router bootstrap ``var b=""`` (including the escaped copy in RSC).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TEXT_EXTENSIONS = {".html", ".js", ".css", ".json", ".xml", ".txt"}
HEAD_INJECT_MARKER = "data-igvf-static-export"

# Force full page loads + fix client-side router paths on static GitHub Pages.
STATIC_HOSTING_SCRIPT = """<script data-igvf-static-export="1">(function(){var B="/__BASE_PATH__";var ROOTS=["/api-reference","/introduction","/using-search","/nodes","/region","/data-sources"];function needsBase(p){if(!p||p===B||p.indexOf(B+"/")===0)return false;for(var i=0;i<ROOTS.length;i++){var r=ROOTS[i];if(p===r||p.indexOf(r+"/")===0)return true}return false}function withBase(path){return needsBase(path)?B+path:path}function fixHref(href){try{var u=new URL(href,location.href);if(u.origin!==location.origin)return href;u.pathname=withBase(u.pathname);return u.pathname+u.search+u.hash}catch(_){return href}}if(needsBase(location.pathname))location.replace(withBase(location.pathname)+location.search+location.hash);["pushState","replaceState"].forEach(function(m){var o=history[m];history[m]=function(s,t,u){if(typeof u==="string"){var fixed=fixHref(u),cur=location.pathname+location.search+location.hash;if(fixed!==cur){location.assign(fixed);return}u=fixed}return o.apply(this,arguments.length===1?[s]:arguments.length===2?[s,t]:[s,t,u])}});function onNav(e){var a=e.target&&e.target.closest&&e.target.closest("a[href]");if(!a||e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||a.hasAttribute("download"))return;var tgt=a.getAttribute("target");if(tgt&&tgt!=="_self")return;var href=a.getAttribute("href");if(!href||href.charAt(0)==="#"||/^(mailto:|tel:|javascript:)/i.test(href))return;var u;try{u=new URL(href,location.href)}catch(_){return}if(u.origin!==location.origin)return;if(needsBase(u.pathname)){e.preventDefault();e.stopImmediatePropagation();location.assign(withBase(u.pathname)+u.search+u.hash);return}if(u.pathname===B||u.pathname.indexOf(B+"/")===0){e.preventDefault();e.stopImmediatePropagation();location.assign(u.href)}}document.addEventListener("click",onNav,true);document.addEventListener("pointerdown",onNav,true)})();</script>"""

# Next.js router bootstrap in HTML and in RSC flight payloads (extra escaping).
RSC_ROUTER_BASE_LITERAL = 'var b=\\\\\\"\\\\\\";'

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


def _patch_router_base(content: str, base_path: str) -> str:
    """Set Next.js router basePath in HTML and embedded RSC bootstrap scripts."""
    content = content.replace('var b="";', f'var b="{base_path}";')
    content = content.replace(
        RSC_ROUTER_BASE_LITERAL,
        f'var b=\\\\\\"{base_path}\\\\\\";',
    )
    return content


def patch_js(content: str, base_path: str) -> str:
    base_path = _normalize_base_path(base_path)
    return _patch_quoted_prefixes(content, base_path, JS_PREFIXES)


def patch_html(content: str, base_path: str) -> str:
    base_path = _normalize_base_path(base_path)

    content = _patch_router_base(content, base_path)
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
