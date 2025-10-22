# services/server/paperclip/ingest.py
from __future__ import annotations

"""
Ingest pipeline with server-side duplicate guarding.

Behavior
--------
- Always ingest the submitted payload into a *new* Capture first (writes artifacts,
  merges strong head meta, extracts references, builds reduced view, indexes).
- Immediately after ingest, we look for duplicates (same DOI or same normalized URL).
- We compute a "detail score" for every candidate (including the brand-new one).
- We *keep* the capture with the highest score and *merge* the others into it:
  - copy over better artifacts (server_parsed/reduced/page/content) when winner lacks them
  - deduplicate and union references
  - re-index the winner
  - delete the losers
- The API returns the winner's id (never leaves dup rows behind).

Rationale
---------
This guarantees no duplicates survive the ingest call, while still allowing us
to parse and measure the submitted payload to compare "detail" fairly.

"More detail" heuristic
-----------------------
- presence of server_parsed.json (+40)
- paragraphs in reduced.sections (+1 per 12 paras, capped)
- references count in server_parsed or reduced (+2 each, capped)
- has DOI/year/title (+10/+3/+1)
- bonus if abstract is present (+5)

The heuristic is intentionally conservative and robust to partial artifacts.

Notes
-----
- This module is drop-in and stays compatible with existing callers.
- Black/Ruff clean (no unused imports, no bare excepts, etc.).
"""

from typing import Any, Mapping
from urllib.parse import urlparse, urlunparse

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from captures.models import Capture, Reference
from captures.reduced_view import CANONICAL_REDUCED_BASENAME, build_reduced_view
from captures.site_parsers import extract_references
from paperclip.artifacts import (
    artifact_path,
    read_json_artifact,
    write_json_artifact,
    write_text_artifact,
)
from paperclip.jobs import submit_enrichment
from paperclip.utils import norm_doi


# We import robust_parse + canonical builder lazily through helpers to keep import
# surfaces small and tolerate refactors in captures.*.
def _build_server_parsed(
    capture: Capture, extraction: dict[str, Any]
) -> dict[str, Any]:
    from captures.artifacts import build_server_parsed as _sp

    return _sp(capture, extraction)


def _robust_parse(
    *, url: str | None, content_html: str, dom_html: str
) -> dict[str, Any]:
    from captures.parsing_bridge import robust_parse as _rp

    return _rp(url=url, content_html=content_html, dom_html=dom_html)


def _host(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").replace("www.", "")
        return host
    except Exception:  # pragma: no cover
        return ""


def _norm_url_for_dup(url: str) -> str:
    """
    Normalize URL for duplicate checks:
    - lowercase scheme+host
    - strip fragment
    - drop trailing slash in path
    - keep query because it may distinguish versions
    """
    try:
        if not url:
            return ""
        u = urlparse(url)
        path = u.path.rstrip("/") or "/"
        return urlunparse(
            (
                (u.scheme or "").lower(),
                (u.netloc or "").lower().replace("www.", ""),
                path,
                u.params,
                u.query,
                "",  # strip fragment
            )
        )
    except Exception:  # pragma: no cover
        return (url or "").strip()


def _ref_kwargs(
    r: Mapping[str, Any], *, capture: Capture, csl_ok: bool = True
) -> dict[str, Any]:
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


def _read_paragraphs_for_score(cap_id: str) -> list[str]:
    """
    Extract paragraph list from reduced view (preferred) or legacy preview fields.
    """
    reduced = read_json_artifact(cap_id, CANONICAL_REDUCED_BASENAME, default={})
    sections = reduced.get("sections") or {}
    # Canonical reduced shape uses structured sections first; fall back to preview paragraphs
    paras: list[str] = []
    if isinstance(sections, dict):
        if isinstance(sections.get("abstract_or_body"), list):
            paras.extend(
                [p for p in sections["abstract_or_body"] if isinstance(p, str)]
            )
        # If canonical uses {"sections":[{"paragraphs":[..]}]}, add those too
        sec_list = sections.get("sections") or sections.get("items")
        if isinstance(sec_list, list):
            for s in sec_list:
                ps = (s or {}).get("paragraphs") or []
                if isinstance(ps, list):
                    paras.extend([p for p in ps if isinstance(p, str)])
    return paras


def _read_reference_count_for_score(cap_id: str) -> int:
    """
    Prefer canonical server_parsed references; fall back to reduced if present.
    """
    sp = read_json_artifact(cap_id, "server_parsed.json", default={})
    if isinstance(sp.get("references"), list):
        return len(sp["references"])
    reduced = read_json_artifact(cap_id, CANONICAL_REDUCED_BASENAME, default={})
    if isinstance(reduced.get("references"), list):
        return len(reduced["references"])
    return 0


def _has_abstract(cap_id: str) -> bool:
    reduced = read_json_artifact(cap_id, CANONICAL_REDUCED_BASENAME, default={})
    if isinstance(reduced.get("abstract"), str) and reduced["abstract"].strip():
        return True
    # Some reduceds put abstract into sections
    sections = reduced.get("sections") or {}
    if isinstance(sections, dict) and isinstance(sections.get("abstract"), str):
        return bool((sections["abstract"] or "").strip())
    return False


def _detail_score_for_existing(cap: Capture) -> int:
    """
    Compute a detail score for an existing capture using its artifacts & fields.
    """
    score = 0
    # Canonical artifacts present?
    sp = read_json_artifact(str(cap.id), "server_parsed.json", default=None)
    if isinstance(sp, dict) and sp:
        score += 40  # strong signal of good parse

    # Paragraph density from reduced view
    paras = _read_paragraphs_for_score(str(cap.id))
    score += min(60, len(paras) // 12)  # +1 per 12 paras, capped

    # References
    score += min(200, _read_reference_count_for_score(str(cap.id)) * 2)

    # Metadata quality
    if norm_doi(cap.doi or (cap.meta or {}).get("doi")):
        score += 10
    if (cap.year or "").strip():
        score += 3
    if (cap.title or "").strip():
        score += 1
    if _has_abstract(str(cap.id)):
        score += 5
    return score


def _detail_score_for_new(
    bridge: Mapping[str, Any], extraction: Mapping[str, Any]
) -> int:
    """
    Lightweight score for the not-yet-committed content based on bridge/extraction.
    """
    score = 0
    meta = (bridge.get("meta_updates") or {}) if isinstance(bridge, Mapping) else {}
    # Sections paragraphs from robust_parse bridge
    sections = (
        (bridge.get("content_sections") or {}) if isinstance(bridge, Mapping) else {}
    )
    paras: list[str] = []
    if isinstance(sections, dict):
        if isinstance(sections.get("abstract_or_body"), list):
            paras.extend(p for p in sections["abstract_or_body"] if isinstance(p, str))
        s_items = sections.get("sections") or sections.get("items")
        if isinstance(s_items, list):
            for s in s_items:
                ps = (s or {}).get("paragraphs") or []
                if isinstance(ps, list):
                    paras.extend([p for p in ps if isinstance(p, str)])
    score += min(60, len(paras) // 12)

    # Client-provided references (rough proxy if present)
    refs = (extraction.get("references") or []) if isinstance(extraction, Mapping) else []  # type: ignore[assignment]
    if isinstance(refs, list):
        score += min(50, len(refs) * 2)

    # Metadata hints
    if norm_doi(meta.get("doi") or (extraction.get("meta") or {}).get("doi")):
        score += 10
    if meta.get("issued_year") or (extraction.get("meta") or {}).get("issued_year"):
        score += 3
    if meta.get("title") or (extraction.get("meta") or {}).get("title"):
        score += 1
    return score


def _candidate_duplicates(new_cap: Capture, bridge: Mapping[str, Any]) -> list[Capture]:
    """
    Find duplicates by normalized DOI or normalized URL, excluding the new capture.
    """
    doi = norm_doi(
        (bridge.get("meta_updates") or {}).get("doi")
        or new_cap.doi
        or (new_cap.meta or {}).get("doi")
    )
    url_key = _norm_url_for_dup(new_cap.url or "")
    qs = Capture.objects.exclude(pk=new_cap.pk)
    filters: list[Q] = []
    if doi:
        filters.append(Q(doi__iexact=doi))
    if url_key:
        # store normalized url_key in-memory (Capture.url is raw); approximate by icontains/iexact
        filters.append(Q(url__iexact=url_key) | Q(url__icontains=url_key))
    if not filters:
        return []
    dupes = qs.filter(filters.pop())
    for f in filters:
        dupes = dupes | qs.filter(f)
    # Deduplicate queryset to a list
    out: list[Capture] = list(dupes.distinct().order_by("-created_at"))
    return out


def _merge_references_into(winner: Capture, from_cap: Capture) -> None:
    """
    Move references from 'from_cap' to 'winner', deduping on normalized DOI then raw.
    """
    existing = Reference.objects.filter(capture=winner).only("id", "doi", "raw")
    existing_doi = {norm_doi(r.doi) for r in existing if r.doi}
    existing_raw = {(r.raw or "").strip().lower() for r in existing if r.raw}

    to_create: list[Reference] = []
    for r in Reference.objects.filter(capture=from_cap).order_by("id"):
        doi_key = norm_doi(r.doi)
        raw_key = (r.raw or "").strip().lower()
        if (doi_key and doi_key in existing_doi) or (
            not doi_key and raw_key in existing_raw
        ):
            continue
        to_create.append(
            Reference(
                capture=winner,
                ref_id=r.ref_id,
                raw=r.raw,
                doi=r.doi,
                title=r.title,
                issued_year=r.issued_year,
                container_title=r.container_title,
                authors=r.authors,
                csl=r.csl,
                volume=r.volume,
                issue=r.issue,
                pages=r.pages,
                publisher=r.publisher,
                issn=r.issn,
                isbn=r.isbn,
                bibtex=r.bibtex,
                apa=r.apa,
                url=r.url,
            )
        )

    if to_create:
        Reference.objects.bulk_create(to_create, batch_size=200)


def _copy_artifact_if_missing(winner: Capture, donor: Capture, basename: str) -> None:
    """
    Copy donor's artifact into winner if winner lacks it.
    """
    w_p = artifact_path(str(winner.id), basename)
    if w_p.exists():
        return
    d_p = artifact_path(str(donor.id), basename)
    if not d_p.exists():
        return
    # Simple byte copy
    w_p.parent.mkdir(parents=True, exist_ok=True)
    w_p.write_bytes(d_p.read_bytes())


def ingest_capture(payload: dict[str, Any]) -> tuple[Capture, dict[str, Any]]:
    """
    Main entry point used by the API.

    Returns
    -------
    (Capture, summary) where Capture is the *winner* after dedupe (may be the
    just-created one or an existing row), and summary is the small JSON block
    returned to the client.
    """
    extraction: dict[str, Any] = payload.get("extraction") or {}
    meta_in: dict[str, Any] = extraction.get("meta") or {}
    csl_in: dict[str, Any] = extraction.get("csl") or {}
    dom_html: str = payload.get("dom_html") or ""
    content_html: str = extraction.get("content_html") or ""
    src_url: str = payload.get("source_url") or ""
    src_host = _host(src_url)

    # 0) Bridge first, so we can (a) override meta strongly and (b) score "new" quality.
    bridge = _robust_parse(url=src_url, content_html=content_html, dom_html=dom_html)
    new_detail_score = _detail_score_for_new(bridge, extraction)

    # 1) Create the Capture row (cheap)
    with transaction.atomic():
        cap = Capture.objects.create(
            url=src_url,
            site=src_host or "",
            title=(meta_in.get("title") or "").strip()
            or (csl_in.get("title") or "").strip(),
            meta=meta_in,
            csl=csl_in or {},
        )

    # 2) Persist verbatim artifacts (page/content snapshots)
    if dom_html:
        write_text_artifact(str(cap.id), "page.html", dom_html)
    if content_html:
        write_text_artifact(str(cap.id), "content.html", content_html)

    # 3) Head/meta + preview/sections (fast path) — merge strong meta into model
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
        blocked = {"title", "doi", "issued_year"}
        passthrough = {k: v for k, v in meta_updates.items() if k not in blocked}
        if passthrough:
            cap.meta = {**(cap.meta or {}), **passthrough}
        if not cap.site:
            cap.site = _host(cap.url or "") or ""
        cap.save(update_fields=["title", "doi", "year", "meta", "site"])

    # 3.5) Synchronous Crossref normalization for the main capture (if DOI present).
    # Keeps downstream exports stable (journal short names, etc.).
    if norm_doi(cap.doi or (cap.meta or {}).get("doi")):
        try:
            from captures.xref import enrich_capture_via_crossref

            upd = enrich_capture_via_crossref(cap)
        except Exception:  # pragma: no cover
            upd = None
        if upd:
            for k, v in upd.items():
                setattr(cap, k, v)
            cap.save(update_fields=list(upd.keys()))

    # 4) Client-provided references
    for r in extraction.get("references") or []:
        Reference.objects.create(**_ref_kwargs(r, capture=cap, csl_ok=True))

    # 5) Site-level references (dedup against any client-provided)
    site_refs = extract_references(cap.url, dom_html)
    if site_refs:
        # normalize/merge site refs against current refs by DOI or raw
        existing_qs = Reference.objects.filter(capture=cap)
        existing_doi = {norm_doi(r.doi) for r in existing_qs if r.doi}
        existing_raw = {(r.raw or "").strip().lower() for r in existing_qs if r.raw}
        to_create = []
        for r in site_refs:
            doi_key = norm_doi(r.get("doi"))
            raw_key = (r.get("raw") or "").strip().lower()
            if (doi_key and doi_key in existing_doi) or (
                not doi_key and raw_key in existing_raw
            ):
                continue
            to_create.append(Reference(**_ref_kwargs(r, capture=cap, csl_ok=False)))
        if to_create:
            Reference.objects.bulk_create(to_create, batch_size=200)

    # 6) Write canonical artifacts using the (possibly enriched) capture data
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

    # 7) Re-index FTS so search picks up abstract/keywords/reduced text immediately
    from captures.search import upsert_capture as _upsert

    _upsert(cap)

    # 8) Optionally queue async enrichment for references (heavy) via background job
    if getattr(settings, "PAPERCLIP_AUTO_ENRICH", True):
        submit_enrichment(str(cap.id))

    # ==============================
    # Duplicate guarding & merging
    # ==============================
    # Consider the new capture and any existing dup candidates.
    candidates = [cap]
    dupes = _candidate_duplicates(cap, bridge)
    candidates.extend(dupes)

    if len(candidates) > 1:
        # Compute detail scores
        scores: dict[str, int] = {}
        for c in candidates:
            if c.pk == cap.pk:
                # "new" score was pre-computed from bridge+extraction
                scores[str(c.id)] = max(new_detail_score, _detail_score_for_existing(c))
            else:
                scores[str(c.id)] = _detail_score_for_existing(c)

        # Pick the winner
        winner = max(candidates, key=lambda c: scores[str(c.id)])
        losers = [c for c in candidates if c.pk != winner.pk]

        if losers:
            with transaction.atomic():
                # If the new capture lost, try to *improve* the winner with missing artifacts/references
                for lost in losers:
                    # union references (dedup by DOI/raw)
                    _merge_references_into(winner, lost)
                    # copy artifacts the winner lacks
                    for base in (
                        "server_parsed.json",
                        CANONICAL_REDUCED_BASENAME,
                        "page.html",
                        "content.html",
                    ):
                        _copy_artifact_if_missing(winner, lost, base)

                # If winner is missing some simple fields and new capture had them, prefer winner's own fields
                # already present; otherwise keep existing winner metadata.

                # Re-index winner after merge
                _upsert(winner)

                # Clean up losers
                for lost in losers:
                    if lost.pk != winner.pk:
                        lost.delete()

            cap = winner  # return the winner's id downstream

    # Tiny summary payload for the extension
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
