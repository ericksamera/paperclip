# services/server/captures/views/captures.py
from __future__ import annotations

import csv
import re
from datetime import datetime
from io import StringIO
from typing import Any, Mapping

from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from captures.exporters import bibtex_entry_for, ris_lines_for
from captures.models import Capture
from captures.reduced_view import read_reduced_view
from captures.types import CSL
from captures.xref import enrich_reference_via_crossref
from paperclip.artifacts import artifact_path
from paperclip.utils import norm_doi

from .common import _author_list, _authors_intext, _journal_full
from .library import _filter_and_rank, _maybe_sort, _search_ids_for_query


# --------------------------------------------------------------------------------------
# Small helper (kept for potential formatting needs)
# --------------------------------------------------------------------------------------
def _first_m_last_from_parts(given: str, family: str) -> str:
    """
    Return 'First M Last' from given/family; includes middle initials if present.
    """
    given = (given or "").replace("·", ".").replace("‧", ".").replace("•", ".").strip()
    family = (family or "").strip()

    def _collapse_initials(s: str) -> str:
        s = re.sub(r"\s*\.\s*", ".", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    # All-initials (e.g. "A. T.")
    if re.fullmatch(r"(?:[A-Za-z]\.\s*)+[A-Za-z]\.?", given):
        return f"{_collapse_initials(given).replace(' ', '')} {family}".strip()

    # First + dotted initials (e.g., "Wendy K. W.")
    m = re.match(r"^([A-Za-z]+)\s+((?:[A-Za-z]\.\s*)+)$", given)
    if m:
        first, initials = m.group(1), _collapse_initials(m.group(2)).replace(" ", "")
        return f"{first} {initials} {family}".strip()

    # Multiple middles without dots -> initials
    parts = given.split()
    if len(parts) >= 2:
        first, middles = parts[0], parts[1:]
        mids = [f"{p[0]}." for p in middles if p]
        return f"{first} {''.join(mids)} {family}".strip()

    return f"{given} {family}".strip()


# --------------------------------------------------------------------------------------
# Capture detail + actions
# --------------------------------------------------------------------------------------
def capture_view(request: HttpRequest, pk: str) -> HttpResponse:
    """
    Render capture detail, populating abstract, sections, and references.

    Provides BOTH keys 'cap' and 'c' for template compatibility (older partials
    sometimes use 'cap', others use 'c').
    """
    cap = get_object_or_404(Capture, pk=pk)

    # Optional HTML snapshot (for the debug panel at the bottom of the page)
    content_html = ""
    p = artifact_path(str(cap.id), "content.html")
    if p.exists():
        content_html = p.read_text(encoding="utf-8")

    # Tolerant reduced-view reader (handles current artifacts and older fallbacks)
    rv = read_reduced_view(str(cap.id)) or {}
    sections_blob = rv.get("sections") or {}

    # Abstract: prefer reduced-view abstract, then DB meta/csl fallback
    csl: CSL | Mapping[str, Any] = cap.csl if isinstance(cap.csl, dict) else {}
    abs_text = (
        (sections_blob.get("abstract") or "")
        or (cap.meta or {}).get("abstract")
        or (csl.get("abstract") if isinstance(csl, Mapping) else "")
        or ""
    )

    # Sections: structured → fallback to preview paragraphs if present
    sections: list[dict[str, Any]] = list(sections_blob.get("sections") or [])
    if not sections:
        paras = sections_blob.get("abstract_or_body") or []
        if isinstance(paras, list) and paras:
            sections = [{"title": "Body", "paragraphs": paras}]

    # References from DB
    refs = cap.references.all().order_by("id")

    # Author line (for header)
    meta = cap.meta or {}
    authors_line = ", ".join([a for a in _author_list(meta, csl) if a]) or ""

    return render(
        request,
        "captures/detail.html",
        {
            "cap": cap,
            "c": cap,
            "content": content_html,
            "abs": abs_text,
            "sections": sections,
            "refs": refs,
            "authors": _author_list(meta, csl),  # legacy list if needed by includes
            "authors_line": authors_line,  # human-friendly line used by template
        },
    )


@require_POST
def capture_delete(request: HttpRequest, pk: str) -> HttpResponseRedirect:
    cap = get_object_or_404(Capture, pk=pk)
    cap.delete()
    return redirect("library")


@require_POST
def capture_bulk_delete(request: HttpRequest) -> HttpResponseRedirect:
    """
    Delete many captures by POSTing ids[]=<id> (or ids=<id>).
    """
    ids = request.POST.getlist("ids[]") or request.POST.getlist("ids")
    if ids:
        Capture.objects.filter(id__in=ids).delete()
    return redirect("library")


def capture_open(_request: HttpRequest, pk: str) -> HttpResponseRedirect:
    cap = get_object_or_404(Capture, pk=pk)
    return HttpResponseRedirect(cap.url or "/")


def capture_artifact(_request: HttpRequest, pk: str, basename: str) -> FileResponse:
    """
    Stream an artifact file (e.g., page.html, content.html, server_parsed.json).
    """
    cap = get_object_or_404(Capture, pk=pk)
    path = artifact_path(str(cap.id), basename)
    try:
        return FileResponse(open(path, "rb"))
    except FileNotFoundError as exc:
        raise Http404("Artifact not found") from exc


def capture_enrich_refs(_request: HttpRequest, pk: str) -> HttpResponse:
    """
    Enrich references for a capture via Crossref; returns a small CSV summary.

    NOTE: This does not *create* references; it enriches ones that already
    exist. If a specific capture has 0 references, they weren’t extracted —
    re‑ingest that item or add an admin repair to parse from page.html.
    """
    cap = get_object_or_404(Capture, pk=pk)
    refs_mgr = getattr(cap, "references", None)
    if not refs_mgr:
        return HttpResponse("No references for this capture", status=404)

    out = StringIO()
    w = csv.writer(out)
    w.writerow(["ref_raw", "doi_in", "doi_out", "title_out"])
    for r in refs_mgr.all():
        doi_in = norm_doi(getattr(r, "doi", "") or "")
        enriched = enrich_reference_via_crossref(r)
        w.writerow(
            [
                (getattr(r, "raw", "") or "")[:120],
                doi_in or "",
                (getattr(enriched, "doi", "") or ""),
                (getattr(enriched, "title", "") or "")[:120],
            ]
        )
    return HttpResponse(out.getvalue(), content_type="text/csv; charset=utf-8")


# --------------------------------------------------------------------------------------
# Library exports (stay in sync with filtering/sorting used by the UI)
# --------------------------------------------------------------------------------------
def _filtered_captures_for_request(request: HttpRequest) -> list[Capture]:
    """
    Mirror LibraryView filtering so exports stay in sync with the UI.
    Respects q/search/year/journal/site/col and sort/dir.
    """
    qterm = (request.GET.get("q") or "").strip()
    search_mode = (request.GET.get("search") or "").strip().lower()
    year = (request.GET.get("year") or "").strip()
    journal = (request.GET.get("journal") or "").strip()
    site = (request.GET.get("site") or "").strip()
    col = (request.GET.get("col") or "").strip()
    sort = request.GET.get("sort")
    direction = request.GET.get("dir") or "desc"

    if qterm:
        ids = _search_ids_for_query(qterm, search_mode)
        filtered, _rank = _filter_and_rank(
            ids, year=year, journal=journal, site=site, col=col
        )
        caps = _maybe_sort(filtered, qterm=qterm, sort=sort, direction=direction)
    else:
        from .common import _apply_filters

        base_qs = Capture.objects.all().order_by("-created_at")
        caps = _apply_filters(base_qs, year=year, journal=journal, site=site, col=col)
        caps = _maybe_sort(caps, qterm=qterm, sort=sort, direction=direction)
    return list(caps)


def capture_export(_request: HttpRequest) -> HttpResponse:
    """
    Simple CSV export (for quick sanity checks or spreadsheets).
    """
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "authors_intext", "year", "journal_short", "doi", "url"])
    for c in Capture.objects.all().order_by("-created_at"):
        meta = c.meta or {}
        csl: CSL | Mapping[str, Any] = c.csl or {}
        title = (
            c.title
            or meta.get("title")
            or ((csl.get("title") if isinstance(csl, Mapping) else "") or "")
            or c.url
            or ""
        ).strip() or "(Untitled)"
        authors = _authors_intext(meta, csl)
        j_full = _journal_full(meta, csl)
        j_short = j_full
        doi = (
            c.doi
            or meta.get("doi")
            or ((csl.get("DOI") if isinstance(csl, Mapping) else "") or "")
            or ""
        ).strip()
        w.writerow([str(c.id), title, authors, c.year, j_short, doi, c.url or ""])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="paperclip_export.csv"'
    return resp


# --- BibTeX export ------------------------------------------------------------
def library_export_bibtex(request: HttpRequest) -> HttpResponse:
    caps = _filtered_captures_for_request(request)
    entries = [bibtex_entry_for(c) for c in caps]
    text = (
        "% Generated by Paperclip\n% Exported: "
        + datetime.utcnow().isoformat(timespec="seconds")
        + "Z\n\n"
        + "\n\n".join(entries)
        + "\n"
    )
    resp = HttpResponse(text, content_type="text/x-bibtex; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="paperclip_export.bib"'
    return resp


# --- RIS export ---------------------------------------------------------------
def library_export_ris(request: HttpRequest) -> HttpResponse:
    caps = _filtered_captures_for_request(request)
    blocks = ["\n".join(ris_lines_for(c)) for c in caps]
    text = "\n".join(blocks) + "\n"
    resp = HttpResponse(
        text, content_type="application/x-research-info-systems; charset=utf-8"
    )
    resp["Content-Disposition"] = 'attachment; filename="paperclip_export.ris"'
    return resp
