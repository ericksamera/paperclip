from __future__ import annotations
import io, zipfile
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from captures.models import Capture, Collection
from paperclip.artifacts import artifact_path


@require_POST
def collection_create(request):
    name = (request.POST.get("name") or "").strip()
    parent_id = request.POST.get("parent") or None
    if not name:
        return redirect("library")
    parent = Collection.objects.filter(pk=parent_id).first() if parent_id else None
    col = Collection.objects.create(name=name, parent=parent)
    return redirect(f"{reverse('library')}?col={col.id}")

@require_POST
def collection_rename(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    name = (request.POST.get("name") or "").strip()
    if name:
        col.name = name
        col.save(update_fields=["name"])
    return redirect(f"{reverse('library')}?col={col.id}")

@require_POST
def collection_delete(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    col.delete()
    return redirect("library")

@require_POST
def collection_assign(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    op = (request.POST.get("op") or "add").lower()
    ids = request.POST.getlist("ids")
    if not ids:
        return redirect(f"{reverse('library')}?col={col.id}")
    qs = Capture.objects.filter(id__in=ids)
    if op == "remove":
        col.captures.remove(*qs)
    else:
        col.captures.add(*qs)
    return redirect(f"{reverse('library')}?col={col.id}")

def collection_download_views(request, cid: str):
    """
    Download a zip of all view.json files for the current collection (or 'all').
    """
    if cid == "all":
        caps = Capture.objects.all()
        label = "all-items"
    else:
        col = get_object_or_404(Collection, pk=int(cid))
        caps = col.captures.all()
        label = f"collection-{col.id}"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in caps:
            p = artifact_path(str(c.id), "view.json")
            if p.exists():
                safe_title = (c.title or str(c.id))[:60].replace("/", "_").replace("\\", "_")
                zf.write(p, arcname=f"{safe_title}__{c.id}_view.json")
    buf.seek(0)
    resp = HttpResponse(buf.read(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{label}-views.zip"'
    return resp
