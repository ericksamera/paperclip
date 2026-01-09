from __future__ import annotations

import re
from typing import Any

from .metaschema import (
    get_abstract,
    get_authors,
    normalize_meta_record,
    parse_meta_json as _parse_meta_json,
)


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
    """
    Accepts either:
      - the normalized meta record (recommended), OR
      - a loosely-shaped dict

    Produces stable display fields for UI.
    """
    if not isinstance(meta, dict):
        meta = {}

    meta = normalize_meta_record(meta)

    authors = get_authors(meta)
    authors_str = ", ".join(authors) if authors else ""
    authors_short = _format_authors_apa_short(authors)

    abstract = get_abstract(meta)
    abstract_snip = _snip_text(abstract, 220) if abstract else ""

    return {
        "authors_str": authors_str,
        "authors_short": authors_short,
        "abstract_snip": abstract_snip,
    }


def citation_fields_from_meta_json(meta_json: Any) -> dict[str, str]:
    meta = normalize_meta_record(_parse_meta_json(meta_json))
    return citation_fields_from_meta(meta)


# Back-compat: keep this symbol stable (a few places historically imported it from citation.py)
def parse_meta_json(meta_json: Any) -> dict[str, Any]:
    return _parse_meta_json(meta_json)
