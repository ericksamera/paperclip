# packages/paperclip-parser/paperclip_parser/html.py
from __future__ import annotations

import re
from typing import Any

from markdownify import markdownify

from paperclip_schemas import Reference, ServerParsed

_SPLIT_RE = re.compile(r"[;,]\s*")


def _kw_list(v: Any) -> list[str]:
    if not v:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [p for p in (s.strip() for s in _SPLIT_RE.split(str(v))) if p]


def parse_html_to_server_parsed(
    cap: Any,  # Django model instance (capture)
    extraction: dict[str, Any] | None,
) -> ServerParsed:
    extraction = extraction or {}
    meta = (extraction.get("meta") or {}).copy()
    csl = (extraction.get("csl") or {}).copy()
    content_html = (extraction.get("content_html") or "") or ""
    if not (extraction.get("rendered") or {}).get("markdown") and content_html:
        markdown = markdownify(content_html)
    else:
        markdown = (extraction.get("rendered") or {}).get("markdown") or ""
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
                issued_year=r.issued_year,
                authors=r.authors,
                csl=r.csl,
                container_title=r.container_title,
            )
        )

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
            [{"title": None, "paragraphs": [csl.get("abstract")]}] if csl.get("abstract") else []
        ),
        body=(
            [{"title": "Body", "paragraphs": [markdown or content_html]}]
            if (markdown or content_html)
            else []
        ),
        keywords=_kw_list(meta.get("keywords")),
        references=refs,
    )
