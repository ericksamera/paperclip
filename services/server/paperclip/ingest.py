# services/server/paperclip/ingest.py
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from django.db import transaction

from captures.models import Capture, Reference
from captures.reduced_view import CANONICAL_REDUCED_BASENAME, build_reduced_view
from captures.site_parsers import dedupe_references, extract_references
from paperclip.artifacts import write_json_artifact, write_text_artifact
from paperclip.conf import AUTO_ENRICH
from paperclip.utils import norm_doi


def _build_server_parsed(capture: Capture, extraction: dict[str, Any]) -> dict[str, Any]:
    from captures.artifacts import build_server_parsed as _sp

    return _sp(capture, extraction)


def _robust_parse(*, url: str | None, content_html: str, dom_html: str) -> dict[str, Any]:
    from captures.parsing_bridge import robust_parse as _rp

    return _rp(url=url, content_html=content_html, dom_html=dom_html)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").replace("www.", "")
    except Exception:
        return ""


def _ref_kwargs(r: dict[str, Any], *, capture: Capture, csl_ok: bool = True) -> dict[str, Any]:
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


def ingest_capture(payload: dict[str, Any]) -> tuple[Capture, dict[str, Any]]:
    extraction: dict[str, Any] = payload.get("extraction") or {}
    meta_in: dict[str, Any] = extraction.get("meta") or {}
    csl_in: dict[str, Any] = extraction.get("csl") or {}
    dom_html: str = payload.get("dom_html") or ""
    content_html: str = extraction.get("content_html") or ""
    src_url: str = payload.get("source_url") or ""
    src_host = _host(src_url)
    # 1) Create the Capture row (cheap)
    with transaction.atomic():
        cap = Capture.objects.create(
            url=src_url,
            site=src_host or "",
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
        BLOCKED_META_KEYS = {"title", "doi", "issued_year"}
        passthrough = {k: v for k, v in meta_updates.items() if k not in BLOCKED_META_KEYS}
        if passthrough:
            cap.meta = {**(cap.meta or {}), **passthrough}
        # Update normalized host if needed
        if not cap.site:
            cap.site = _host(cap.url or "") or ""
        cap.save(update_fields=["title", "doi", "year", "meta", "site"])
    # 4) Client-provided references
    for r in extraction.get("references") or []:
        Reference.objects.create(**_ref_kwargs(r, capture=cap, csl_ok=True))
    # 5) Site-level references (dedup against client)
    site_refs = dedupe_references(extract_references(cap.url, dom_html))
    with transaction.atomic():
        existing_qs = Reference.objects.filter(capture=cap)
        existing_doi = {norm_doi(r.doi) for r in existing_qs if r.doi}
        existing_raw = {(r.raw or "").strip().lower() for r in existing_qs if r.raw}
        to_create = []
        for r in site_refs:
            doi_key = norm_doi(r.get("doi"))
            raw_key = (r.get("raw") or "").strip().lower()
            if (doi_key and doi_key in existing_doi) or (not doi_key and raw_key in existing_raw):
                continue
            to_create.append(Reference(**_ref_kwargs(r, capture=cap, csl_ok=False)))
        if to_create:
            Reference.objects.bulk_create(to_create, batch_size=200)
    # 6) Write canonical artifacts ONLY (no legacy doc.json/view.json)
    server_parsed = _build_server_parsed(cap, extraction)
    write_json_artifact(str(cap.id), "server_parsed.json", server_parsed)
    reduced = build_reduced_view(
        content=bridge.get("content_sections") or {},
        meta=server_parsed.get("metadata") or (cap.meta or {}),
        references=[
            {
                "raw": r.raw,
                "doi": r.doi,
                "issued_year": r.issued_year,
                "apa": r.apa,
                "title": r.title,
            }
            for r in Reference.objects.filter(capture=cap).order_by("id")
        ],
        title=(server_parsed.get("title") or cap.title or ""),
    )
    write_json_artifact(str(cap.id), CANONICAL_REDUCED_BASENAME, reduced)
    # NEW: re-index so FTS picks up reduced view & keywords
    from captures.search import upsert_capture as _upsert

    _upsert(cap)
    from paperclip.jobs import submit_enrichment

    if AUTO_ENRICH:
        submit_enrichment(str(cap.id))
    first_three = list(Reference.objects.filter(capture=cap).order_by("id")[:3])
    first_three_simple = [{"apa": r.apa, "doi": r.doi} for r in first_three]
    summary = {
        "title": cap.title,
        "url": cap.url,
        "reference_count": Reference.objects.filter(capture=cap).count(),
        "figure_count": len(extraction.get("figures") or []),
        "table_count": len(extraction.get("tables") or []),
        "first_3_references": first_three_simple,
    }
    return cap, summary
