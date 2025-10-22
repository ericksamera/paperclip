# services/server/captures/views/collections.py
from __future__ import annotations

import io
import json
import re
import unicodedata
import zipfile
from typing import Any, Mapping

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from captures.models import Capture, Collection
from captures.reduced_view import read_reduced_view
from captures.types import CSL
from paperclip.journals import get_short_journal_name

from .common import _author_list, _family_from_name, _journal_full


def _ascii_slug(s: str) -> str:
    """
    Fold accents → ASCII, keep [a-z0-9-], collapse dashes, lowercase.
    """
    s = (
        unicodedata.normalize("NFKD", (s or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    s = re.sub(r"-{2,}", "-", s)
    return s


def _slug_for_capture(c: Capture) -> str:
    """
    {year}_{first-author-family-name}_{journal-short-name}
    Fallbacks: year='na', author='anon', journal='journal'
    """
    meta: Mapping[str, Any] = c.meta or {}
    csl: CSL | Mapping[str, Any] = c.csl or {}
    year = (
        c.year or meta.get("year") or meta.get("publication_year") or ""
    ).strip() or "na"
    authors = _author_list(meta, csl)
    fam = _family_from_name(authors[0]) if authors else ""
    fam_slug = _ascii_slug(fam or "anon") or "anon"
    j_full = _journal_full(meta, csl)
    j_short = get_short_journal_name(j_full, csl) or j_full or "journal"
    j_slug = _ascii_slug(j_short) or "journal"
    return f"{year}_{fam_slug}_{j_slug}"


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
    force = (request.POST.get("force") or "").strip() == "1"

    has_children = col.children.exists()
    has_items = col.captures.exists()

    if (has_children or has_items) and not force:
        msg = "Collection is not empty. Re-run with force=1 to delete."
        from django.http import HttpResponseBadRequest

        return HttpResponseBadRequest(msg)

    # If forcing, clear items and reparent children to the parent (if any) before delete
    if force:
        parent = col.parent
        if has_items:
            col.captures.clear()
        if has_children:
            for child in col.children.all():
                child.parent = parent
                child.save(update_fields=["parent"])

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
    Download a zip of all reduced views for the given collection id.
    Global (all) exports are disabled by default, behind a setting.
    """
    from django.conf import settings
    from django.http import HttpResponseBadRequest

    allow_global = bool(getattr(settings, "ALLOW_GLOBAL_VIEW_EXPORTS", False))
    if cid == "all" and not allow_global:
        return HttpResponseBadRequest(
            "Global view export is disabled. Choose a collection to export its views."
        )

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
            view = read_reduced_view(str(c.id))
            if not view:
                continue
            slug = _slug_for_capture(c)
            arcname = f"{slug}__{c.id}.json"
            zf.writestr(arcname, json.dumps(view, ensure_ascii=False, indent=2))
    buf.seek(0)
    resp = HttpResponse(buf.read(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{label}-views.zip"'
    return resp
