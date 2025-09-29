# services/server/paperclip/ingest.py
from __future__ import annotations
from typing import Any, Dict, Tuple

from django.db import transaction

from captures.models import Capture, Reference
from captures.reduced_view import build_reduced_view
from captures.site_parsers import extract_references, dedupe_references
from captures.xref import enrich_capture_via_crossref, enrich_reference_via_crossref
from paperclip.artifacts import write_json_artifact, write_text_artifact
from paperclip.conf import AUTO_ENRICH, MAX_REFS_TO_ENRICH
from paperclip.utils import norm_doi


# Import at call-time so tests can patch via module path
def _build_server_parsed(capture, extraction):
    from captures.artifacts import build_server_parsed as _sp
    return _sp(capture, extraction)

def _robust_parse(*, url: str | None, content_html: str, dom_html: str) -> Dict[str, Any]:
    from captures.parsing_bridge import robust_parse as _rp  # lazy import for patchability
    return _rp(url=url, content_html=content_html, dom_html=dom_html)


def _ref_kwargs(r: Dict[str, Any], *, capture: Capture, csl_ok: bool = True) -> Dict[str, Any]:
    """
    Build safe kwargs for Reference(), ensuring ref_id is never NULL.
    csl_ok=False for site-parsed refs where we don't carry CSL.
    """
    return {
        "capture": capture,
        "ref_id": (r.get("id") or ""),                       # never None
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


def ingest_capture(payload: Dict[str, Any]) -> Tuple[Capture, Dict[str, Any]]:
    """
    Orchestrate ingest with SHORT DB transactions to avoid SQLite write-locks.
    Returns (capture, summary).
    """
    extraction: Dict[str, Any] = payload.get("extraction") or {}
    meta_in: Dict[str, Any] = extraction.get("meta") or {}
    csl_in: Dict[str, Any] = extraction.get("csl") or {}
    dom_html: str = payload.get("dom_html") or ""
    content_html: str = extraction.get("content_html") or ""
    src_url: str = payload.get("source_url") or ""

    # 1) Create Capture row with minimal fields; keep transaction short
    with transaction.atomic():
        cap = Capture.objects.create(
            url=src_url,
            # seed title from client/csl, but we will override with strong head meta below
            title=(meta_in.get("title") or "").strip() or (csl_in.get("title") or "").strip(),
            meta=meta_in,
            csl=csl_in or {},
        )

    # 2) Persist artifacts we always want to keep verbatim (HTML stays on disk, not DB)
    if dom_html:
        write_text_artifact(str(cap.id), "page.html", dom_html)
    if content_html:
        write_text_artifact(str(cap.id), "content.html", content_html)

    # 3) Head/meta bridge (robust_parse) for strong head and preview paragraphs
    bridge = _robust_parse(url=src_url, content_html=content_html, dom_html=dom_html)
    meta_updates = bridge.get("meta_updates") or {}

    # Always prefer strong head meta for title/doi/year,
    # and merge the rest into cap.meta.
    if meta_updates:
        # Promoted fields
        new_title = meta_updates.get("title")
        new_doi = meta_updates.get("doi")
        new_year = meta_updates.get("issued_year")

        if new_title:
            cap.title = new_title
        if new_doi:
            cap.doi = new_doi
        if new_year is not None:
            cap.year = str(new_year or "")

        # Merge remaining keys into meta
        passthrough = {k: v for k, v in meta_updates.items() if k not in {"title", "doi", "issued_year"}}
        if passthrough:
            cap.meta = {**(cap.meta or {}), **passthrough}

        cap.save(update_fields=["title", "doi", "year", "meta"])

    # 4) Client-provided references as-is (no dedupe here)
    for r in (extraction.get("references") or []):
        Reference.objects.create(**_ref_kwargs(r, capture=cap, csl_ok=True))

    # 5) Site-level references (parse, compute de-dupes, then one small write)
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

    # 6) Optional auto-enrichment (NO transaction; each save is tiny)
    if AUTO_ENRICH:
        try:
            upd = enrich_capture_via_crossref(cap)
            if upd:
                for k, v in upd.items():
                    setattr(cap, k, v)
                cap.save(update_fields=list(upd.keys()))
        except Exception:
            pass

        count = 0
        for ref in cap.references.all().order_by("id"):
            if count >= MAX_REFS_TO_ENRICH:
                break
            if not ref.doi:
                continue
            try:
                upd = enrich_reference_via_crossref(ref)
                if upd:
                    for k, v in upd.items():
                        setattr(ref, k, v)
                    ref.save(update_fields=list(upd.keys()))
            except Exception:
                pass
            count += 1

    # 7) Write canonical + reduced JSON (legacy filenames to satisfy current clients/tests)
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

    summary = {
        "title": cap.title,
        "url": cap.url,
        "reference_count": cap.references.count(),
        "figure_count": len((extraction.get("figures") or [])),
        "table_count": len((extraction.get("tables") or [])),
        "first_3_references": [{"apa": r.apa, "doi": r.doi} for r in cap.references.all().order_by("id")[:3]],
    }
    return cap, summary
