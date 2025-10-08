# services/server/captures/views/captures.py
from __future__ import annotations

import csv
import re
import unicodedata
from datetime import datetime
from io import StringIO
from typing import Any, Mapping

from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render

from captures.models import Capture
from captures.reduced_view import read_reduced_view
from captures.exporters import bibtex_entry_for, ris_lines_for
from captures.xref import enrich_reference_via_crossref
from captures.types import CSL
from paperclip.artifacts import artifact_path
from paperclip.utils import norm_doi

from .common import _author_list, _authors_intext, _journal_full
from .library import _filter_and_rank, _maybe_sort, _search_ids_for_query


# --------------------------------------------------------------------------------------
# Author name helpers
# --------------------------------------------------------------------------------------
def _first_m_last_from_parts(given: str, family: str) -> str:
    """
    Return 'First M Last' from given/family; includes middle initials if present.

    Rules:
      - If the entire `given` is initials (e.g., "A.T." / "A. T."), collapse spaces: "A.T."
      - If `given` contains a first name + dotted initials (e.g., "Wendy K. W."),
        keep a space before the initials block, collapse spaces within the block: "Wendy K.W."
      - If there are extra middle names without dots (e.g., "John Allen Paul"),
        render as "John A. Paul".
    """
    given = (given or "").strip()
    family = (family or "").strip()
    if not (given or family):
        return ""

    comp = given.replace(" ", "")
    if re.fullmatch(r"(?:[A-Za-z]\.){1,4}", comp):
        giv_fmt = comp  # collapse spaces between dotted initials only
        return (giv_fmt + (" " + family if family else "")).strip()

    if "." in given and " " in given:
        parts = re.split(r"\s+", given)
        first = parts[0]
        tail = "".join(parts[1:])  # "K.W."
        giv_fmt = first + (" " + tail if tail else "")
        return (giv_fmt + (" " + family if family else "")).strip()

    # No dots: turn middle names into initials
    parts = re.split(r"\s+", given) if given else []
    first = parts[0] if parts else ""
    mids = parts[1:]
    mid_inits = [m[0].upper() + "." for m in mids if m and m[0].isalpha()]
    giv_fmt = " ".join([p for p in [first, *mid_inits] if p])
    return (giv_fmt + (" " + family if family else "")).strip()


def _authors_line(meta: Mapping[str, Any], csl: CSL | Mapping[str, Any]) -> str:
    """
    Build a single string 'First M Last, First Last, ...' preferring CSL authors.
    """
    names: list[tuple[str, str]] = []

    # Prefer CSL authors
    try:
        csl_auth = (csl or {}).get("author")  # type: ignore[index]
    except Exception:
        csl_auth = None
    if isinstance(csl_auth, list):
        for a in csl_auth:
            if isinstance(a, dict):
                fam = (a.get("family") or a.get("last") or "").strip()
                giv = (a.get("given") or a.get("first") or "").strip()
                if fam or giv:
                    names.append((giv, fam))

    # Fallback: meta.authors as before
    if not names and isinstance(meta, Mapping) and isinstance(meta.get("authors"), list):
        for a in meta["authors"]:
            if isinstance(a, dict):
                fam = (a.get("family") or a.get("last") or "").strip()
                giv = (a.get("given") or a.get("first") or "").strip()
                if fam or giv:
                    names.append((giv, fam))
            elif isinstance(a, str):
                s = a.strip()
                m = re.match(r"^\s*([^,]+),\s*(.+?)\s*$", s)
                if m:
                    fam = m.group(1).strip()
                    giv = m.group(2).strip()
                    names.append((giv, fam))
                else:
                    parts = s.split()
                    if len(parts) >= 2:
                        fam = parts[-1]
                        giv = " ".join(parts[:-1])
                        names.append((giv, fam))
                    else:
                        names.append((s, ""))

    formatted = [_first_m_last_from_parts(g, f) for (g, f) in names if (g or f)]
    seen: set[str] = set()
    uniq: list[str] = []
    for n in formatted:
        k = n.lower()
        if n and k not in seen:
            seen.add(k)
            uniq.append(n)
    return ", ".join(uniq)


# --------------------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------------------
def capture_view(request: HttpRequest, pk: str) -> HttpResponse:
    cap = get_object_or_404(Capture, pk=pk)

    # Optional HTML snapshot for the debug panel
    content = ""
    p = artifact_path(str(cap.id), "content.html")
    if p.exists():
        content = p.read_text(encoding="utf-8")

    # Load reduced sections (tolerant reader)
    rv = read_reduced_view(str(cap.id))
    sections_blob = rv.get("sections") or {}

    # Abstract (prefer reduced-view abstract, then DB meta/csl)
    csl: CSL | Mapping[str, Any] = cap.csl if isinstance(cap.csl, dict) else {}
    abs_text = (
        (sections_blob.get("abstract") or "")
        or (cap.meta or {}).get("abstract")
        or (csl.get("abstract") if isinstance(csl, Mapping) else "")
        or ""
    )

    # Sections (structured tree or fallback to preview paragraphs)
    sections: list[dict[str, Any]] = list(sections_blob.get("sections") or [])
    if not sections:
        paras = sections_blob.get("abstract_or_body") or []
        if isinstance(paras, list) and paras:
            sections = [{"title": "Body", "paragraphs": paras}]

    refs = cap.references.all().order_by("id")
    meta = cap.meta or {}
    authors_line = _authors_line(meta, csl)

    return render(
        request,
        "captures/detail.html",
        {
            "cap": cap,
            "content": content,
            "refs": refs,
            "abs": abs_text,
            "sections": sections,
            "authors": _author_list(meta, csl),  # legacy list if needed
            "authors_line": authors_line,        # human-friendly line
        },
    )



def capture_open(_request: HttpRequest, pk: str) -> HttpResponse:
    cap = get_object_or_404(Capture, pk=pk)
    if not cap.url:
        return HttpResponse("No URL for this capture", status=404)
    return HttpResponseRedirect(cap.url)


def capture_delete(request: HttpRequest, pk: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse(status=405)
    cap = get_object_or_404(Capture, pk=pk)
    cap.delete()
    return redirect("library")


def capture_bulk_delete(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse(status=405)
    ids = request.POST.getlist("ids")
    if ids:
        Capture.objects.filter(id__in=ids).delete()
    return redirect("library")


def capture_enrich_refs(request: HttpRequest, pk: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse(status=405)
    cap = get_object_or_404(Capture, pk=pk)
    for r in cap.references.all().order_by("id"):
        try:
            upd = enrich_reference_via_crossref(r)
        except Exception:
            upd = None
        if upd:
            for k, v in upd.items():
                setattr(r, k, v)
            r.save(update_fields=list(upd.keys()))
    return redirect("capture_view", pk=str(cap.id))


def capture_export(_request: HttpRequest) -> HttpResponse:
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "authors_intext", "year", "journal_short", "doi", "url"])
    for c in Capture.objects.all().order_by("-created_at"):
        meta = c.meta or {}
        csl: CSL | Mapping[str, Any] = c.csl or {}
        title = (c.title or meta.get("title") or (csl.get("title") if isinstance(csl, Mapping) else "") or c.url or "").strip() or "(Untitled)"
        authors = _authors_intext(meta, csl)
        j_full = _journal_full(meta, csl)
        j_short = j_full
        doi = (c.doi or meta.get("doi") or (csl.get("DOI") if isinstance(csl, Mapping) else "") or "").strip()
        w.writerow([str(c.id), title, authors, c.year, j_short, doi, c.url or ""])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="paperclip_export.csv"'
    return resp


def capture_artifact(_request: HttpRequest, pk: str, basename: str) -> FileResponse:
    """
    Serve an artifact file for a capture, with graceful fallbacks between
    canonical and legacy basenames so links never 404.
    """
    cap = get_object_or_404(Capture, pk=pk)
    FALLBACKS: dict[str, list[str]] = {
        # canonical → legacy
        "server_parsed.json": ["doc.json"],
        "server_output_reduced.json": ["view.json", "parsed.json"],
        # legacy → canonical (so old links keep working too)
        "doc.json": ["server_parsed.json"],
        "view.json": ["server_output_reduced.json"],
        "parsed.json": ["server_output_reduced.json"],
    }
    candidates = [basename, *FALLBACKS.get(basename, [])]
    path = None
    for name in candidates:
        p = artifact_path(str(cap.id), name)
        if p.exists():
            path = p
            break
    if path is None:
        raise Http404("Artifact not found")
    # keep prior behavior: show text for .json/.html/.txt
    if path.suffix in {".json", ".html", ".txt"}:
        return FileResponse(path.open("rb"), content_type="text/plain; charset=utf-8")
    return FileResponse(path.open("rb"))


# --------------------------------------------------------------------------------------
# Library exports (respect current filters / search params)
# --------------------------------------------------------------------------------------
def _filtered_captures_for_request(request: HttpRequest) -> list[Capture]:
    from .common import _apply_filters

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
        filtered, _rank = _filter_and_rank(ids, year=year, journal=journal, site=site, col=col)
        caps = _maybe_sort(filtered, qterm=qterm, sort=sort, direction=direction)
    else:
        base_qs = Capture.objects.all().order_by("-created_at")
        caps = _apply_filters(base_qs, year=year, journal=journal, site=site, col=col)
        caps = _maybe_sort(caps, qterm="", sort=sort, direction=direction)
    return caps


def _ascii_slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    s = re.sub(r"-{2,}", "-", s)
    return s or "item"


def _year_of(c: Capture) -> str:
    meta = c.meta or {}
    y = c.year or meta.get("year") or meta.get("publication_year")
    try:
        return str(int(y))
    except Exception:
        return str(y or "")



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
    resp = HttpResponse(text, content_type="application/x-research-info-systems; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="paperclip_export.ris"'
    return resp
