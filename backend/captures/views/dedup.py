from __future__ import annotations

import shutil
from contextlib import suppress

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from captures.models import Capture
from captures.references.merge import merge_captures
from captures.reduced_view import read_reduced_view
from captures.services.dedup import (
    group_key,
    ignored_set,
    read_dupes,
    scan_and_write_dupes,
    write_ignored,
)

from .common import _journal_full


def _format_added(dt):
    if not dt:
        return "", ""
    delta = timezone.now() - dt
    days = int(delta.total_seconds() // 86400)
    if days <= 0:
        return "today", dt.isoformat()
    if days == 1:
        return "yesterday", dt.isoformat()
    return f"{days}d ago", dt.isoformat()


def _preview_for(c: Capture) -> str:
    """
    Small, stable preview for the dedup table:
      1) Prefer reduced view -> sections.abstract_or_body (first 1-3 paras)
      2) Fallback to meta.abstract or csl.abstract
    """
    view = read_reduced_view(str(c.id))
    paras = (view.get("sections") or {}).get("abstract_or_body") or []
    txt = " ".join(paras[:3] or [])
    if txt:
        import re as _re

        txt = _re.sub(r"\s+", " ", txt).strip()
        return (txt[:280] + ".") if len(txt) > 280 else txt
    meta = c.meta or {}
    csl = c.csl or {}
    return meta.get("abstract") or csl.get("abstract") or ""


def dedup_review(request):
    groups = read_dupes()
    ignored = ignored_set()
    show_all = request.GET.get("all") == "1"

    vis_groups = []
    for g in groups:
        key = group_key(g)
        if not show_all and key in ignored:
            continue
        vis_groups.append(g)

    decorated = []
    for g in vis_groups:
        rows = []
        for pk in g:
            c = Capture.objects.filter(pk=pk).first()
            if not c:
                continue
            added_h, added_iso = _format_added(c.created_at)
            rows.append(
                {
                    "id": str(c.id),
                    "title": c.title or "(Untitled)",
                    "doi": c.doi or "",
                    "year": c.year or "",
                    "journal": _journal_full(c.meta or {}, c.csl or {}),
                    "added": added_h,
                    "added_iso": added_iso,
                    "preview": _preview_for(c),
                }
            )
        if len(rows) > 1:
            decorated.append(rows)
    return render(
        request,
        "captures/dupes.html",
        {"groups": decorated, "ignored_count": len(ignored), "all_mode": show_all},
    )


@require_POST
def dedup_scan_view(_request):
    scan_and_write_dupes(threshold=0.85)
    return redirect("dedup_review")


@require_POST
def dedup_ignore(request):
    ids = request.POST.getlist("ids")
    if not ids:
        return redirect("dedup_review")
    ignored = ignored_set()
    ignored.add(group_key(ids))
    write_ignored(ignored)
    return redirect("dedup_review")


@require_POST
def dedup_merge(request):
    primary_id = request.POST.get("primary")
    others = request.POST.getlist("others")
    if not primary_id or not others:
        if "application/json" in (request.headers.get("Accept") or ""):
            return JsonResponse({"ok": False, "error": "bad_request"}, status=400)
        return redirect("dedup_review")

    primary = get_object_or_404(Capture, pk=primary_id)
    from django.conf import settings as _s
    from captures.search import upsert_capture as _upsert

    # transactional merge
    removed: list[str] = []
    with transaction.atomic():
        for oid in others:
            if oid == primary_id:
                continue
            dup = Capture.objects.filter(pk=oid).first()
            if not dup:
                continue

            # Use the shared merge helper: refs + artifacts + collections
            merge_captures(primary, dup)
            removed.append(str(oid))

            # Remove dup artifacts folder on disk (UI behavior)
            with suppress(Exception):
                shutil.rmtree((_s.ARTIFACTS_DIR / str(oid)), ignore_errors=True)

            # Delete the loser row
            dup.delete()

        # Re-index the primary after merging everything into it
        _upsert(primary)

    # mark this group as handled
    ignored = ignored_set()
    ids = [primary_id, *others]
    ignored.add(group_key(ids))
    write_ignored(ignored)

    wants_json = "application/json" in (request.headers.get("Accept") or "")
    if wants_json:
        return JsonResponse(
            {
                "ok": True,
                "primary": str(primary_id),
                "removed": removed,
                "ignored_key": group_key(ids),
            }
        )
    return redirect("dedup_review")
