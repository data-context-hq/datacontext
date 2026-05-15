from __future__ import annotations

import hashlib
import re
from typing import Any


_STRING_RE = re.compile(r"('([^']|'')*'|\"([^\"]|\"\")*\")")
_NUMBER_RE = re.compile(r"\b\d+(\.\d+)?\b")
_WHITESPACE_RE = re.compile(r"\s+")
_IN_RE = re.compile(r"\bin\s*\((\s*\?\s*,?)+\)", re.IGNORECASE)


def normalize_query(query: Any) -> str:
    text = str(query)
    text = _STRING_RE.sub("?", text)
    text = _NUMBER_RE.sub("?", text)
    text = _WHITESPACE_RE.sub(" ", text).strip().lower()
    text = _IN_RE.sub("in (?)", text)
    return text


def fingerprint_query(query: Any) -> str:
    try:
        normalized = normalize_query(query)
        digest = hashlib.sha256(normalized.encode("utf-8", "replace")).hexdigest()
        return f"sha256:{digest}"
    except Exception:
        return "unknown"

