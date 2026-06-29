"""Shared helpers for loading OpenAPI from Catalog Swagger UI bundles."""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"[ \t]+")

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


def normalize_html_description(text: str) -> str:
    """Convert Swagger HTML line breaks to Markdown-friendly paragraphs."""
    if not text or "<br" not in text.lower():
        return text
    text = BR_TAG_RE.sub("\n", text)
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n\n".join(lines)


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
