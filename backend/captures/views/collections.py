# services/server/captures/views/collections.py
from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from captures.models import Capture, Collection
from captures.types import CSL
from paperclip.journals import get_short_journal_name

from captures.services.collections import (
    export_views_zip,
    delete_collection,
    assign_captures,
)

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

    ok, error = delete_collection(col, force=force)
    if not ok:
        from django.http import HttpResponseBadRequest

        return HttpResponseBadRequest(error or "Collection is not empty.")
    return redirect("library")


@require_POST
def collection_assign(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    op = (request.POST.get("op") or "add").lower()
    ids = request.POST.getlist("ids")
    if not ids:
        return redirect(f"{reverse('library')}?col={col.id}")

    assign_captures(col, ids, op)
    return redirect(f"{reverse('library')}?col={col.id}")


def collection_download_views(
    request: HttpRequest, pk: str | None = None
) -> HttpResponse:
    """
    Download a zip of reduced views:

      - If pk provided: only that collection's captures
      - If no pk: all captures
    """
    if pk is not None:
        col = get_object_or_404(Collection, pk=pk)
        caps = col.captures.all().order_by("-created_at")
        filename = (col.slug or col.name or "collection").strip() or "collection"
        filename = f"{filename}.zip"
    else:
        caps = Capture.objects.all().order_by("-created_at")
        filename = "all_captures_views.zip"

    data = export_views_zip(caps)
    resp = HttpResponse(data, content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
