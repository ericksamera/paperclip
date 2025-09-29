from __future__ import annotations
import csv
from io import StringIO

from django.http import Http404, HttpResponse, FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect

from captures.models import Capture, Reference
from captures.xref import enrich_reference_via_crossref
from paperclip.artifacts import artifact_path

from .common import _authors_intext, _journal_full


def capture_view(request, pk):
    cap = get_object_or_404(Capture, pk=pk)
    content = ""
    p = artifact_path(str(cap.id), "content.html")
    if p.exists():
        content = p.read_text(encoding="utf-8")
    csl = cap.csl if isinstance(csl := cap.csl, dict) else {}
    abs_text = (cap.meta or {}).get("abstract") or csl.get("abstract") or ""
    refs = cap.references.all().order_by("id")
    return render(request, "captures/detail.html", {"cap": cap, "content": content, "refs": refs, "abs": abs_text})

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
    w.writerow(["id","title","authors_intext","year","journal_short","doi","url"])
    for c in Capture.objects.all().order_by("-created_at"):
        meta = c.meta or {}; csl = c.csl or {}
        title = (c.title or meta.get("title") or csl.get("title") or c.url or "").strip() or "(Untitled)"
        authors = _authors_intext(meta, csl)
        j_full = _journal_full(meta, csl)
        j_short = j_full  # short name is computed in template path, keep CSV simple here
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
