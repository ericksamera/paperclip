# packages/paperclip-parser/paperclip_parser/html.py
from __future__ import annotations

import re
from typing import Any, List

from markdownify import markdownify

from paperclip_schemas import Reference, ServerParsed, Table
from .tables import extract_tables as _extract_tables

_SPLIT_RE = re.compile(r"[;,\s]\s*")


def _kw_list(v: Any) -> list[str]:
    if not v:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    # split on comma/semicolon and collapse whitespace
    return [p for p in (s.strip() for s in re.split(r"[;,]\s*", str(v))) if p]


def _coerce_tables(obj: Any) -> List[Table]:
    """Accept pre-supplied tables (list[dict]) or derive from content_html."""
    out: List[Table] = []
    if isinstance(obj, list) and obj:
        for t in obj:
            if isinstance(t, dict):
                try:
                    out.append(Table(**t))
                except Exception:
                    # best-effort: tolerate slightly different keys
                    out.append(
                        Table(
                            id=str(t.get("id") or "") or None,
                            title=str(t.get("title") or "") or None,
                            caption=str(t.get("caption") or "") or None,
                            source_link=str(t.get("source_link") or "") or None,
                            columns=[str(x) for x in (t.get("columns") or [])],
                            rows=[[str(x) for x in r] for r in (t.get("rows") or [])],
                            records=[
                                {str(k): str(v) for k, v in d.items()}
                                for d in (t.get("records") or [])
                            ],
                        )
                    )
    return out


def parse_html_to_server_parsed(
    cap: Any,  # Django model instance (capture)
    extraction: dict[str, Any] | None,
) -> ServerParsed:
    extraction = extraction or {}
    meta = (extraction.get("meta") or {}).copy()
    csl = (extraction.get("csl") or {}).copy()
    content_html = (extraction.get("content_html") or "") or ""

    # markdown body fallback if client didn't include rendered.markdown
    if not (extraction.get("rendered") or {}).get("markdown") and content_html:
        markdown = markdownify(content_html)
    else:
        markdown = (extraction.get("rendered") or {}).get("markdown") or ""

    # --- references from DB (unchanged) ---
    refs: list[Reference] = []
    if hasattr(cap, "references"):
        refs_iter = cap.references
        iterable = refs_iter.all() if hasattr(refs_iter, "all") else refs_iter
    else:
        iterable = []

    for r in iterable:
        refs.append(
            Reference(
                id=r.ref_id or None,
                raw=r.raw,
                title=r.title,
                doi=r.doi,
                url=r.url,
                issued_year=(
                    (int(r.issued_year) if str(r.issued_year).isdigit() else None)
                    if getattr(r, "issued_year", None) not in (None, "")
                    else None
                ),
                authors=r.authors,
                csl=r.csl,
                container_title=r.container_title,
            )
        )

    # --- NEW: tables ---
    # 1) honor incoming extraction.tables if present
    tables = _coerce_tables(extraction.get("tables"))

    # 2) otherwise, derive from content_html
    if not tables and content_html:
        try:
            raw_tables = _extract_tables(content_html)  # list[dict]
            tables = [Table(**t) for t in raw_tables]
        except Exception:
            tables = []

    return ServerParsed(
        id=str(cap.id),
        title=cap.title,
        url=cap.url,
        doi=cap.doi,
        metadata={
            **meta,
            "title": cap.title,
            "doi": cap.doi,
            "issued_year": cap.year,
            "url": cap.url,
            "csl": csl,
        },
        abstract=(
            [{"title": None, "paragraphs": [csl.get("abstract")]}]
            if csl.get("abstract")
            else []
        ),
        body=(
            [{"title": "Body", "paragraphs": [markdown or content_html]}]
            if (markdown or content_html)
            else []
        ),
        keywords=_kw_list(meta.get("keywords")),
        references=refs,
        tables=tables,
    )
