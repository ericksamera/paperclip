# services/server/paperclip/ingest.py
from __future__ import annotations
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

from django.db import transaction

from captures.models import Capture, Reference
from captures.reduced_view import build_reduced_view
from captures.site_parsers import extract_references, dedupe_references
from captures.xref import enrich_capture_via_crossref, enrich_reference_via_crossref
from paperclip.artifacts import write_json_artifact, write_text_artifact
from paperclip.conf import AUTO_ENRICH, MAX_REFS_TO_ENRICH
from paperclip.utils import norm_doi


def _build_server_parsed(capture, extraction):
    from captures.artifacts import build_server_parsed as _sp
    return _sp(capture, extraction)

def _robust_parse(*, url: str | None, content_html: str, dom_html: str) -> Dict[str, Any]:
    from captures.parsing_bridge import robust_parse as _rp
    return _rp(url=url, content_html=content_html, dom_html=dom_html)

def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").replace("www.", "")
    except Exception:
        return ""

def _ref_kwargs(r: Dict[str, Any], *, capture: Capture, csl_ok: bool = True) -> Dict[str, Any]:
    return {
        "capture": capture,
        "ref_id": (r.get("id") or ""),
        "raw": r.get("raw", ""),
        "doi": r.get("doi", ""),
        "title": r.get("title", ""),
        "issued_year": str(r.get("issued_year") or ""),
        "container_title": r.get("container_title", ""),
        "authors": (r.get("authors") or []),
        "csl": (r.get("csl", {}) if csl_ok else {}),
        "volume": r.get("volume", ""),
        "issue": r.get("issue", ""),
        "pages": r.get("pages", ""),
        "publisher": r.get("publisher", ""),
        "issn": r.get("issn", ""),
        "isbn": r.get("isbn", ""),
        "bibtex": r.get("bibtex", ""),
        "apa": r.get("apa", ""),
        "url": r.get("url", ""),
    }

# services/server/paperclip/ingest.py (function replacement)
def ingest_capture(payload: Dict[str, Any]) -> Tuple[Capture, Dict[str, Any]]:
    extraction: Dict[str, Any] = payload.get("extraction") or {}
    meta_in: Dict[str, Any] = extraction.get("meta") or {}
    csl_in: Dict[str, Any] = extraction.get("csl") or {}
    dom_html: str = payload.get("dom_html") or ""
    content_html: str = extraction.get("content_html") or ""
    src_url: str = payload.get("source_url") or ""
    src_host = _host(src_url)

    # 1) Create the Capture row (cheap)
    with transaction.atomic():
        cap = Capture.objects.create(
            url=src_url,
            site=src_host,
            title=(meta_in.get("title") or "").strip() or (csl_in.get("title") or "").strip(),
            meta=meta_in,
            csl=csl_in or {},
        )

    # 2) Persist verbatim artifacts
    if dom_html:
        write_text_artifact(str(cap.id), "page.html", dom_html)
    if content_html:
        write_text_artifact(str(cap.id), "content.html", content_html)

    # 3) Head/meta + preview/sections (fast path)
    bridge = _robust_parse(url=src_url, content_html=content_html, dom_html=dom_html)
    meta_updates = bridge.get("meta_updates") or {}

    if meta_updates:
        new_title = meta_updates.get("title")
        new_doi = meta_updates.get("doi")
        new_year = meta_updates.get("issued_year")

        if new_title:
            cap.title = new_title
        if new_doi:
            cap.doi = new_doi
        if new_year is not None:
            cap.year = str(new_year or "")

        passthrough = {k: v for k, v in meta_updates.items() if k not in {"title", "doi", "issued_year"}}
        if passthrough:
            cap.meta = {**(cap.meta or {}), **passthrough}

        # Update normalized host if needed
        if not cap.site:
            cap.site = _host(cap.url or "")

        cap.save(update_fields=["title", "doi", "year", "meta", "site"])

    # 4) Client-provided references
    for r in (extraction.get("references") or []):
        Reference.objects.create(**_ref_kwargs(r, capture=cap, csl_ok=True))

    # 5) Site-level references (dedup against client)
    site_refs = dedupe_references(extract_references(cap.url, dom_html))
    with transaction.atomic():
        existing_doi = {norm_doi(r.doi) for r in cap.references.all() if r.doi}
        existing_raw = {(r.raw or "").strip().lower() for r in cap.references.all() if r.raw}
        to_create = []
        for r in site_refs:
            doi_key = norm_doi(r.get("doi"))
            raw_key = (r.get("raw") or "").strip().lower()
            if (doi_key and doi_key in existing_doi) or (not doi_key and raw_key in existing_raw):
                continue
            to_create.append(Reference(**_ref_kwargs(r, capture=cap, csl_ok=False)))
        if to_create:
            Reference.objects.bulk_create(to_create, batch_size=200)

    # 6) Write canonical + reduced JSON **now** so sections appear immediately
    doc = _build_server_parsed(cap, extraction)
    write_json_artifact(str(cap.id), "doc.json", doc)

    view = build_reduced_view(
        content=bridge.get("content_sections") or {},
        meta=cap.meta,
        references=[
            {"raw": r.raw, "doi": r.doi, "issued_year": r.issued_year, "apa": r.apa, "title": r.title}
            for r in cap.references.all().order_by("id")
        ],
        title=cap.title,
    )
    write_json_artifact(str(cap.id), "view.json", view)

    # NEW: re-index once more so FTS picks up view.json/body & keywords
    try:
        from captures.search import upsert_capture as _upsert
        _upsert(cap)
    except Exception:
        pass

    # 7) (Optional) queue enrichment instead of blocking
    from paperclip.jobs import submit_enrichment
    if AUTO_ENRICH:
        submit_enrichment(str(cap.id))

    summary = {
        "title": cap.title,
        "url": cap.url,
        "reference_count": cap.references.count(),
        "figure_count": len((extraction.get("figures") or [])),
        "table_count": len((extraction.get("tables") or [])),
        "first_3_references": [{"apa": r.apa, "doi": r.doi} for r in cap.references.all().order_by("id")[:3]],
    }
    return cap, summary
