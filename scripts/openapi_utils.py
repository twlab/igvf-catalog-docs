"""Shared helpers for loading OpenAPI from Catalog Swagger UI bundles."""

from __future__ import annotations

import json
import urllib.request
from typing import Any


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
