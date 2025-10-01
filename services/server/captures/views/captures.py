# services/server/captures/views/captures.py
from __future__ import annotations
import csv, re
from io import StringIO

from django.http import Http404, HttpResponse, FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect

from captures.models import Capture, Reference
from captures.xref import enrich_reference_via_crossref
from paperclip.artifacts import artifact_path
from .common import _authors_intext, _journal_full, _author_list


def _first_m_last_from_parts(given: str, family: str) -> str:
    """Return 'First M Last' from given/family; includes middle initials if present."""
    given = (given or "").strip()
    family = (family or "").strip()
    if not (given or family):
        return ""
    # If given already looks like initials (e.g., "A.T."), keep it as-is.
    if re.search(r"[A-Za-z]\.", given):
        giv_fmt = re.sub(r"\s+", "", given)
    else:
        parts = re.split(r"\s+", given) if given else []
        first = parts[0] if parts else ""
        mids = parts[1:]
        mid_inits = [m[0].upper() + "." for m in mids if m and m[0].isalpha()]
        giv_fmt = " ".join([p for p in [first] + mid_inits if p])
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

    # Format
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
    from django.shortcuts import get_object_or_404, render
    from paperclip.artifacts import artifact_path, read_json_artifact
    from captures.models import Capture

    cap = get_object_or_404(Capture, pk=pk)

    # Optional HTML snapshot for the debug panel
    content = ""
    p = artifact_path(str(cap.id), "content.html")
    if p.exists():
        content = p.read_text(encoding="utf-8")

    # Load reduced sections
    def _read_reduced_sections(cap_id: str) -> dict:
        for name in ("view.json", "server_output_reduced.json", "parsed.json"):
            data = read_json_artifact(str(cap_id), name, default=None)
            if isinstance(data, dict) and data.get("sections"):
                return data["sections"] or {}
        return {}

    reduced = _read_reduced_sections(cap.id)

    # Abstract
    csl = cap.csl if isinstance(cap.csl, dict) else {}
    abs_text = (
        (reduced.get("abstract") or "")
        or (cap.meta or {}).get("abstract")
        or csl.get("abstract")
        or ""
    )

    # Sections
    sections = list(reduced.get("sections") or [])
    if not sections:
        paras = reduced.get("abstract_or_body") or []
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
            "authors": _author_list(meta, csl),     # still available if needed anywhere else
            "authors_line": authors_line,           # NEW: 'First M Last, ...'
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
        title = (c.title or meta.get("title") or csl.get("title") or c.url or "").strip() or "(Untitled)"
        authors = _authors_intext(meta, csl)
        j_full = _journal_full(meta, csl)
        j_short = j_full
        doi = (c.doi or meta.get("doi") or csl.get("DOI") or "").strip()
        w.writerow([str(c.id), title, authors, c.year, j_short, doi, c.url or ""])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="paperclip_export.csv"'
    return resp


def capture_artifact(_request, pk, basename: str):
    cap = get_object_or_404(Capture, pk=pk)
    p = artifact_path(str(cap.id), basename)
    if not p.exists():
        raise Http404("Artifact not found")
    if p.suffix in {".json", ".html", ".txt"}:
        return FileResponse(open(p, "rb"), content_type="text/plain; charset=utf-8")
    return FileResponse(open(p, "rb"))
