from __future__ import annotations

import json
import re
from typing import Any


def _snip_text(s: str, n: int = 200) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _author_last_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return ""
    parts = re.split(r"\s+", name)
    return parts[-1].strip(",") if parts else name


def _format_authors_apa_short(authors: list[str]) -> str:
    authors = [a for a in (authors or []) if (a or "").strip()]
    if not authors:
        return ""
    if len(authors) == 1:
        return _author_last_name(authors[0])
    if len(authors) == 2:
        return f"{_author_last_name(authors[0])} & {_author_last_name(authors[1])}"
    return f"{_author_last_name(authors[0])} et al."


def citation_fields_from_meta(meta: dict[str, Any]) -> dict[str, str]:
    if not isinstance(meta, dict):
        meta = {}

    authors_in = meta.get("authors") or meta.get("author") or []
    authors: list[str] = []

    if isinstance(authors_in, list):
        for a in authors_in:
            if isinstance(a, str):
                if a.strip():
                    authors.append(a.strip())
            elif isinstance(a, dict):
                family = (
                    a.get("family") or a.get("last") or a.get("last_name") or ""
                ).strip()
                given = (
                    a.get("given") or a.get("first") or a.get("first_name") or ""
                ).strip()
                name = (a.get("name") or "").strip()
                if family and given:
                    authors.append(f"{given} {family}".strip())
                elif family:
                    authors.append(family)
                elif name:
                    authors.append(name)

    authors_str = ", ".join(authors) if authors else ""
    authors_short = _format_authors_apa_short(authors)

    abstract = meta.get("abstract") or meta.get("description") or ""
    abstract_snip = _snip_text(str(abstract), 220) if abstract else ""

    return {
        "authors_str": authors_str,
        "authors_short": authors_short,
        "abstract_snip": abstract_snip,
    }


def citation_fields_from_meta_json(meta_json: Any) -> dict[str, str]:
    try:
        meta = json.loads(meta_json) if meta_json else {}
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return citation_fields_from_meta(meta)


def parse_meta_json(meta_json: Any) -> dict[str, Any]:
    try:
        v = json.loads(meta_json) if meta_json else {}
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}
