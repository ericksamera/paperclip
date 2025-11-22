# services/server/captures/artifacts.py
from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from django.conf import settings


def _import_parser() -> Callable[..., Any] | None:
    """
    Try to import the parser package. If it's not pip-installed, try the monorepo
    path (.../packages/paperclip-parser/) and import again. Return the callable
    parse_html_to_server_parsed or None.
    """
    # 1) Normal import (pip/venv)
    with suppress(Exception):
        mod = importlib.import_module("paperclip_parser")
        fn = getattr(mod, "parse_html_to_server_parsed", None)
        if callable(fn):
            return fn
    # 2) Monorepo fallback: add packages/paperclip-parser to sys.path
    with suppress(Exception):
        root = getattr(settings, "MONOREPO_ROOT", None)
        if root:
            pkg_dir = Path(root) / "packages" / "paperclip-parser"
            if pkg_dir.exists():
                p = str(pkg_dir)
                if p not in sys.path:
                    sys.path.insert(0, p)
                mod = importlib.import_module("paperclip_parser")
                fn = getattr(mod, "parse_html_to_server_parsed", None)
                if callable(fn):
                    return fn
    return None


def build_server_parsed(cap: Any, extraction: dict[str, Any]) -> dict[str, Any]:
    """
    Canonical adapter to the parser package with a strong, content-rich fallback.
    Always returns a plain dict so json.dump works and downstream .get() calls are safe.
    """
    parse = _import_parser()
    if parse:
        try:
            out = parse(cap, extraction)  # expected signature
            # Normalize to plain dict regardless of model type (Pydantic v1/v2 support)
            if isinstance(out, dict):
                return out
            if hasattr(out, "model_dump"):
                return out.model_dump()
            if hasattr(out, "dict"):
                return out.dict()
        except Exception:
            # fall through to rich fallback
            pass
    # Parser missing or failed -> rich fallback using robust_parse + DB refs
    return _rich_fallback_doc(cap, extraction)


def _rich_fallback_doc(cap: Any, extraction: dict[str, Any]) -> dict[str, Any]:
    """
    Better-than-minimal fallback:
      • merges head/meta from robust_parse (abstract, preview paras, keywords)
      • carries client meta/CSL through 'metadata'
      • includes DB references (if available)
    """
    # Safe imports here to avoid circulars at module import time
    from captures.parsing_bridge import robust_parse

    extraction = extraction or {}
    meta_in = (extraction.get("meta") or {}).copy()
    csl_in = (extraction.get("csl") or {}).copy()
    content_html = (extraction.get("content_html") or "") or ""
    dom_html = ""  # we don't need it for the fallback; robust_parse handles without
    # Strong meta + preview/sections
    try:
        bridge = robust_parse(
            url=getattr(cap, "url", None), content_html=content_html, dom_html=dom_html
        )
    except Exception:
        bridge = {"meta_updates": {}, "content_sections": {}}
    mu = bridge.get("meta_updates") or {}
    sections = bridge.get("content_sections") or {}
    abs_txt = (sections.get("abstract") or "") if isinstance(sections, dict) else ""
    paras = (
        (sections.get("abstract_or_body") or []) if isinstance(sections, dict) else []
    )
    # Build abstract/body sections
    abstract = [{"title": None, "paragraphs": [abs_txt]}] if abs_txt else []
    body = [{"title": "Body", "paragraphs": [p for p in paras if p]}] if paras else []
    # Keywords: prefer robust_parse → fall back to client meta
    keywords = list(mu.get("keywords") or meta_in.get("keywords") or [])
    if isinstance(keywords, str):
        keywords = [keywords]
    # References from DB if present
    refs: list[dict[str, Any]] = []
    try:
        refs_attr = getattr(cap, "references", None)
        if refs_attr is not None and hasattr(refs_attr, "all"):
            for r in refs_attr.all():
                refs.append(
                    {
                        "id": r.ref_id or None,
                        "raw": r.raw,
                        "title": r.title,
                        "doi": r.doi,
                        "url": r.url,
                        "issued_year": r.issued_year,
                        "authors": r.authors,
                        "csl": r.csl or {},
                        "container_title": r.container_title,
                    }
                )
    except Exception:
        refs = []
    title = getattr(cap, "title", "") or meta_in.get("title") or ""
    url = getattr(cap, "url", None)
    doi = getattr(cap, "doi", None)
    year = getattr(cap, "year", None)
    # Merge a compact metadata dict (client meta + CSL + core fields)
    metadata = {
        **(meta_in or {}),
        "title": title,
        "doi": doi,
        "issued_year": year,
        "url": url,
        "csl": csl_in or {},
    }
    return {
        "id": str(getattr(cap, "id", "")) or "fallback",
        "title": title,
        "url": url,
        "doi": doi,
        "metadata": metadata,
        "abstract": abstract,
        "body": body,
        "keywords": keywords,
        "references": refs,
    }
