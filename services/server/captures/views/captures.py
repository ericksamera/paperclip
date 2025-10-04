# services/server/captures/views/captures.py
from __future__ import annotations

import csv
import re
from io import StringIO

from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render

from captures.models import Capture
from captures.reduced_view import read_reduced_view
from captures.xref import enrich_reference_via_crossref
from paperclip.artifacts import artifact_path

from .common import _author_list, _authors_intext, _journal_full


def _first_m_last_from_parts(given: str, family: str) -> str:
    """
    Return 'First M Last' from given/family; includes middle initials if present.

    Rules:
      - If the entire `given` is initials (e.g., "A.T." or "A. T."), collapse spaces: "A.T."
      - If `given` contains a regular first name plus dotted initials (e.g., "Wendy K. W."),
        keep a space between the first name and the initials block, while collapsing spaces
        INSIDE the initials block: "Wendy K.W."
      - If there are extra middle names without dots (e.g., "John Allen Paul"), render
        as "John A. Paul".
    """
    given = (given or "").strip()
    family = (family or "").strip()
    if not (given or family):
        return ""

    # 1) Pure-initials 'given' (e.g., "A. T." / "A.T." / "M.E.")
    comp = given.replace(" ", "")
    if re.fullmatch(r"(?:[A-Za-z]\.){1,4}", comp):
        giv_fmt = comp  # collapse spaces between dotted initials only
        return (giv_fmt + (" " + family if family else "")).strip()

    # 2) Mixed: first name + dotted initials somewhere in the rest (e.g., "Wendy K. W.")
    if "." in given and " " in given:
        parts = re.split(r"\s+", given)
        first = parts[0]
        tail = "".join(parts[1:])  # collapse spaces between tokens -> "K.W." (if they were "K. W.")
        giv_fmt = first + (" " + tail if tail else "")
        return (giv_fmt + (" " + family if family else "")).strip()

    # 3) No dots: turn middle names into initials
    parts = re.split(r"\s+", given) if given else []
    first = parts[0] if parts else ""
    mids = parts[1:]
    mid_inits = [m[0].upper() + "." for m in mids if m and m[0].isalpha()]
    giv_fmt = " ".join([p for p in [first, *mid_inits] if p])

    return (giv_fmt + (" " + family if family else "")).strip()


def _authors_line(meta: dict, csl: dict) -> str:
    """
    Build a single string 'First M Last, First Last, ...' preferring CSL authors
    (family/given). Falls back to meta.authors which may be 'Family, Given' strings.
    """
    names: list[tuple[str, str]] = []
    # Prefer CSL
    if isinstance(csl, dict) and isinstance(csl.get("author"), list) and csl["author"]:
        for a in csl["author"]:
            fam = (a.get("family") or a.get("last") or "").strip()
            giv = (a.get("given") or a.get("first") or "").strip()
            if fam or giv:
                names.append((giv, fam))
    # Fallback: meta.authors (strings or dicts)
    if not names and isinstance(meta, dict) and isinstance(meta.get("authors"), list):
        for a in meta["authors"]:
            if isinstance(a, dict):
                fam = (a.get("family") or a.get("last") or "").strip()
                giv = (a.get("given") or a.get("first") or "").strip()
                if fam or giv:
                    names.append((giv, fam))
            elif isinstance(a, str):
                s = a.strip()
                # Try "Family, Given"
                m = re.match(r"^\s*([^,]+),\s*(.+?)\s*$", s)
                if m:
                    fam = m.group(1).strip()
                    giv = m.group(2).strip()
                    names.append((giv, fam))
                else:
                    # Heuristic: last token is family
                    parts = s.split()
                    if len(parts) >= 2:
                        fam = parts[-1]
                        giv = " ".join(parts[:-1])
                        names.append((giv, fam))
                    else:
                        names.append((s, ""))

    # Format with improved spacing/initials handling
    formatted = [_first_m_last_from_parts(g, f) for (g, f) in names if (g or f)]
    # De-dup while keeping order (case-insensitive)
    seen = set()
    uniq = []
    for n in formatted:
        k = n.lower()
        if n and k not in seen:
            seen.add(k)
            uniq.append(n)
    return ", ".join(uniq)


def capture_view(request, pk):
    from django.shortcuts import get_object_or_404

    from captures.models import Capture
    from paperclip.artifacts import artifact_path

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
    csl = cap.csl if isinstance(cap.csl, dict) else {}
    abs_text = (
        (sections_blob.get("abstract") or "")
        or (cap.meta or {}).get("abstract")
        or csl.get("abstract")
        or ""
    )
    # Sections (structured tree or fallback to preview paragraphs)
    sections = list(sections_blob.get("sections") or [])
    if not sections:
        paras = sections_blob.get("abstract_or_body") or []
        if isinstance(paras, list) and paras:
            sections = [{"title": "Body", "paragraphs": paras}]
    refs = cap.references.all().order_by("id")
    # Author strings
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
            "authors": _author_list(meta, csl),  # still available if needed anywhere else
            "authors_line": authors_line,  # 'First M Last, ...' with correct spacing
        },
    )


def capture_open(request, pk):
    cap = get_object_or_404(Capture, pk=pk)
    if not cap.url:
        return HttpResponse("No URL for this capture", status=404)
    return HttpResponseRedirect(cap.url)


def capture_delete(request, pk):
    if request.method != "POST":
        return HttpResponse(status=405)
    cap = get_object_or_404(Capture, pk=pk)
    cap.delete()
    return redirect("library")


def capture_bulk_delete(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    ids = request.POST.getlist("ids")
    if ids:
        Capture.objects.filter(id__in=ids).delete()
    return redirect("library")


def capture_enrich_refs(request, pk):
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


def capture_export(_request):
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "authors_intext", "year", "journal_short", "doi", "url"])
    for c in Capture.objects.all().order_by("-created_at"):
        meta = c.meta or {}
        csl = c.csl or {}
        title = (
            c.title or meta.get("title") or csl.get("title") or c.url or ""
        ).strip() or "(Untitled)"
        authors = _authors_intext(meta, csl)
        j_full = _journal_full(meta, csl)
        j_short = j_full
        doi = (c.doi or meta.get("doi") or csl.get("DOI") or "").strip()
        w.writerow([str(c.id), title, authors, c.year, j_short, doi, c.url or ""])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="paperclip_export.csv"'
    return resp


def capture_artifact(_request, pk, basename: str):
    """
    Serve an artifact file for a capture, with graceful fallbacks between
    canonical and legacy basenames so links never 404.
    """
    cap = get_object_or_404(Capture, pk=pk)
    FALLBACKS = {
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
