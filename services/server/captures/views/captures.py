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

from captures.models import Capture
from captures.reduced_view import read_reduced_view
from captures.exporters import bibtex_entry_for, ris_lines_for
from captures.types import CSL
from captures.xref import enrich_reference_via_crossref
from paperclip.artifacts import artifact_path
from paperclip.utils import norm_doi

from .common import _authors_intext, _journal_full
from .library import _filter_and_rank, _maybe_sort, _search_ids_for_query


# --------------------------------------------------------------------------------------
# Optional name helper kept for future formatting needs
# --------------------------------------------------------------------------------------
def _first_m_last_from_parts(given: str, family: str) -> str:
    given = (given or "").replace("·", ".").replace("‧", ".").replace("•", ".").strip()
    family = (family or "").strip()

    def _collapse_initials(s: str) -> str:
        s = re.sub(r"\s*\.\s*", ".", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    # All-initials (e.g., "A. T.")
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
def capture_view(request: HttpRequest, pk) -> HttpResponse:
    """
    Render capture detail. Provide BOTH keys 'cap' and 'c' for template
    compatibility (some partials expect 'cap', others 'c').
    """
    cap = get_object_or_404(Capture, pk=pk)
    context = {
        "cap": cap,  # <- old partials expect this
        "c": cap,  # <- newer includes sometimes use this
        "view": read_reduced_view(str(cap.id)),
    }
    return render(request, "captures/detail.html", context)


@require_POST
def capture_delete(request: HttpRequest, pk) -> HttpResponseRedirect:
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


def capture_open(_request: HttpRequest, pk) -> HttpResponseRedirect:
    cap = get_object_or_404(Capture, pk=pk)
    return HttpResponseRedirect(cap.url or "/")


def capture_artifact(_request: HttpRequest, pk, basename: str) -> FileResponse:
    cap = get_object_or_404(Capture, pk=pk)
    path = artifact_path(str(cap.id), basename)
    try:
        return FileResponse(open(path, "rb"))
    except FileNotFoundError:
        raise Http404("Artifact not found")


def capture_enrich_refs(_request: HttpRequest, pk) -> HttpResponse:
    """
    Enrich references for a capture via Crossref; returns CSV summary.
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
# Filtering helper shared by exports
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
        caps = _maybe_sort(caps, qterm="", sort=sort, direction=direction)
    return caps


# --------------------------------------------------------------------------------------
# CSV export (broad, legacy behavior kept)
# --------------------------------------------------------------------------------------
def capture_export(_request: HttpRequest) -> HttpResponse:
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "authors_intext", "year", "journal_short", "doi", "url"])
    for cap in Capture.objects.all().order_by("-created_at"):
        meta = cap.meta or {}
        csl: CSL | Mapping[str, Any] = cap.csl or {}
        title = (
            cap.title
            or meta.get("title")
            or (csl.get("title") if isinstance(csl, Mapping) else "")
            or cap.url
            or ""
        ).strip() or "(Untitled)"
        authors = _authors_intext(meta, csl)
        j_full = _journal_full(meta, csl)
        j_short = j_full  # keep simple; project has short-name helper elsewhere
        doi = (
            cap.doi
            or meta.get("doi")
            or (csl.get("DOI") if isinstance(csl, Mapping) else "")
            or ""
        ).strip()
        w.writerow([str(cap.id), title, authors, cap.year, j_short, doi, cap.url or ""])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="paperclip_export.csv"'
    return resp


# --------------------------------------------------------------------------------------
# Collection-scoped exports (new guard)
# --------------------------------------------------------------------------------------
def _require_collection_id(
    request: HttpRequest,
) -> tuple[str | None, HttpResponse | None]:
    """
    All BibTeX/RIS exports must be explicitly scoped to a collection (?col=<id>).
    Returns (col_id, error_response).
    """
    col = (request.GET.get("col") or "").strip()
    if not col:
        return None, HttpResponse(
            "This export must be scoped to a collection (?col=<id>).", status=400
        )
    return col, None


def library_export_bibtex(request: HttpRequest) -> HttpResponse:
    col, err = _require_collection_id(request)
    if err:
        return err
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


def library_export_ris(request: HttpRequest) -> HttpResponse:
    col, err = _require_collection_id(request)
    if err:
        return err
    caps = _filtered_captures_for_request(request)
    blocks = ["\n".join(ris_lines_for(c)) for c in caps]
    text = "\n".join(blocks) + "\n"
    resp = HttpResponse(
        text, content_type="application/x-research-info-systems; charset=utf-8"
    )
    resp["Content-Disposition"] = 'attachment; filename="paperclip_export.ris"'
    return resp


# Back-compat aliases in case urls/__init__.py still import old names
def capture_export_bibtex(request: HttpRequest) -> HttpResponse:  # pragma: no cover
    return library_export_bibtex(request)


def capture_export_ris(request: HttpRequest) -> HttpResponse:  # pragma: no cover
    return library_export_ris(request)
