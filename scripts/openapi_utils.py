"""Shared helpers for loading OpenAPI from Catalog Swagger UI bundles."""

from __future__ import annotations

import json
import re
import urllib.request
from html.parser import HTMLParser
from typing import Any

# Matches real HTML tags (e.g. <div ...>, </p>, <br/>) but not bare "<"/"<="
# that appear in descriptions (e.g. "lt (<), lte (<=)").
HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")

HTTP_METHODS = ("get", "post", "put", "delete", "patch", "options", "head")

# Expand or fix the casing of path words that don't title-case cleanly.
TITLE_WORD_OVERRIDES = {
    "freq": "Frequency",
    "ld": "Linkage Disequilibrium",
    "qtl": "QTL",
    "qtls": "QTLs",
    "go": "GO",
    "gnomad": "gnomAD",
    "llm": "LLM",
    "id": "ID",
    "ids": "IDs",
}


def _title_word(word: str) -> str:
    return TITLE_WORD_OVERRIDES.get(word.lower(), word.capitalize())


def title_from_path(path: str) -> str:
    """Build a human-readable English title from an API path.

    Path parameters (``{...}`` segments) are skipped, remaining segments are
    split on hyphens and title-cased, e.g. ``/variants/freq`` -> "Variants
    Frequency".
    """
    words: list[str] = []
    for segment in path.split("/"):
        if not segment or segment.startswith("{"):
            continue
        for part in segment.split("-"):
            if part:
                words.append(_title_word(part))
    return " ".join(words)


def assign_operation_summaries(spec: dict[str, Any]) -> dict[str, Any]:
    """Set a readable ``summary`` (page title) on each operation lacking one."""
    for path, operations in (spec.get("paths") or {}).items():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            if not operation.get("summary"):
                operation["summary"] = title_from_path(path)
    return spec


# Inline tags wrap their text content with the given Markdown markers.
_INLINE_WRAP = {"strong": "**", "b": "**", "em": "*", "i": "*", "code": "`"}
# Tags whose content is dropped entirely (interactive tab buttons can't work in
# static docs and merely duplicate the panel headings below them).
_DROP_TAGS = {"button"}
# Tags that introduce a block (paragraph) boundary.
_BLOCK_TAGS = {"p", "div", "ul", "ol"}


class _HtmlToMarkdown(HTMLParser):
    """Convert the small subset of HTML used in Swagger descriptions to Markdown."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[Any]) -> None:
        if self._skip:
            self._skip += 1
            return
        if tag in _DROP_TAGS:
            self._skip = 1
        elif tag in _INLINE_WRAP:
            self._out.append(_INLINE_WRAP[tag])
        elif tag in _BLOCK_TAGS:
            self._out.append("\n\n")
        elif tag == "li":
            self._out.append("\n- ")
        elif tag == "br":
            self._out.append("\n\n")

    def handle_startendtag(self, tag: str, attrs: list[Any]) -> None:
        if not self._skip and tag == "br":
            self._out.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip:
            self._skip -= 1
            return
        if tag in _INLINE_WRAP:
            self._out.append(_INLINE_WRAP[tag])
        elif tag in _BLOCK_TAGS:
            self._out.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        # Collapse runs of whitespace but keep existing blank-line paragraph breaks.
        parts = [re.sub(r"\s+", " ", part) for part in re.split(r"\n[ \t]*\n", data)]
        self._out.append("\n\n".join(parts))

    def result(self) -> str:
        text = "".join(self._out)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def normalize_html_description(text: str) -> str:
    """Convert HTML in a Swagger description to Markdown so it renders, not escapes."""
    if not text or not HTML_TAG_RE.search(text):
        return text
    parser = _HtmlToMarkdown()
    parser.feed(text)
    return parser.result()


def normalize_openapi_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Rewrite operation/parameter descriptions that use HTML <br> tags."""

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("description", "summary") and isinstance(value, str):
                    node[key] = normalize_html_description(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return spec


def load_spec_from_swagger_init(swagger_init_url: str, timeout: float = 120) -> dict[str, Any]:
    text = urllib.request.urlopen(swagger_init_url, timeout=timeout).read().decode("utf-8")
    key = '"swaggerDoc":'
    i = text.find(key)
    if i < 0:
        raise RuntimeError("swaggerDoc not found in swagger-ui-init.js")
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


def load_config(path: str = "openapi/config.json") -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
