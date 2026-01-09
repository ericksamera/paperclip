from __future__ import annotations

import json
from typing import Any


def parse_meta_json(meta_json: Any) -> dict[str, Any]:
    """
    Parse captures.meta_json (JSON string or dict) into a dict.
    Guaranteed to return a dict.
    """
    if isinstance(meta_json, dict):
        return dict(meta_json)
    if not meta_json:
        return {}
    try:
        v = json.loads(meta_json)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _dedupe_str_list(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        s = str(it or "").strip()
        if not s:
            continue
        k = s.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _person_to_name(v: Any) -> str:
    """
    Convert common author dict shapes into a display name string.
    """
    if isinstance(v, str):
        return v.strip()
    if not isinstance(v, dict):
        return str(v).strip()

    family = str(v.get("family") or v.get("last") or v.get("last_name") or "").strip()
    given = str(v.get("given") or v.get("first") or v.get("first_name") or "").strip()
    name = str(v.get("name") or "").strip()

    if given and family:
        return f"{given} {family}".strip()
    if family:
        return family
    if name:
        return name
    return ""


def get_head_meta(meta: dict[str, Any]) -> dict[str, Any]:
    v = meta.get("meta")
    return dict(v) if isinstance(v, dict) else {}


def get_keywords(meta: dict[str, Any]) -> list[str]:
    v = meta.get("keywords")
    if v is None:
        return []
    if isinstance(v, str):
        return _dedupe_str_list([v])
    if isinstance(v, list):
        return _dedupe_str_list([str(x).strip() for x in v if str(x or "").strip()])
    return []


def get_authors(meta: dict[str, Any]) -> list[str]:
    """
    Stable author list output. Accepts:
      - list[str]
      - list[dict] (family/given/name)
      - str
    """
    v = meta.get("authors")
    if v is None:
        return []

    if isinstance(v, str):
        return _dedupe_str_list([v])

    if isinstance(v, list):
        out: list[str] = []
        for a in v:
            name = _person_to_name(a)
            if name:
                out.append(name)
        return _dedupe_str_list(out)

    return []


def get_abstract(meta: dict[str, Any]) -> str:
    v = meta.get("abstract")
    if v is None:
        return ""
    if not isinstance(v, str):
        v = str(v)
    return v.strip()


def get_published_date_raw(meta: dict[str, Any]) -> str:
    v = meta.get("published_date_raw")
    if v is None:
        return ""
    if not isinstance(v, str):
        v = str(v)
    return v.strip()


def get_client(meta: dict[str, Any]) -> dict[str, Any]:
    v = meta.get("client")
    return dict(v) if isinstance(v, dict) else {}


def normalize_meta_record(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure the meta record has stable keys + types for templates/exports.
    Preserves any extra keys present.
    """
    if not isinstance(meta, dict):
        meta = {}

    out = dict(meta)
    out["meta"] = get_head_meta(out)
    out["keywords"] = get_keywords(out)
    out["authors"] = get_authors(out)
    out["abstract"] = get_abstract(out)
    out["published_date_raw"] = get_published_date_raw(out)
    out["client"] = get_client(out)
    return out


def build_meta_record(
    *,
    head_meta: dict[str, Any] | None,
    keywords: Any = None,
    authors: Any = None,
    abstract: Any = None,
    published_date_raw: Any = None,
    client: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Canonical constructor for captures.meta_json.

    - head_meta: raw head meta dict (lowercased keys typically)
    - keywords/authors/abstract/published_date_raw/client: extracted normalized fields
    - extra: any additional keys you want to persist at top-level
    """
    base: dict[str, Any] = {
        "meta": dict(head_meta) if isinstance(head_meta, dict) else {},
        "keywords": keywords if keywords is not None else [],
        "authors": authors if authors is not None else [],
        "abstract": abstract if abstract is not None else "",
        "published_date_raw": (
            published_date_raw if published_date_raw is not None else ""
        ),
        "client": client if isinstance(client, dict) else {},
    }
    if isinstance(extra, dict) and extra:
        base.update(extra)
    return normalize_meta_record(base)
