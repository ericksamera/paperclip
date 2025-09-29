from __future__ import annotations
import json, shutil

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from captures.models import Capture, Reference

from .common import _journal_full


def _read_dupes():
    p = settings.ANALYSIS_DIR / "dupes.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("groups") or []
    except Exception:
        return []

def _ignored_set() -> set[str]:
    p = settings.ANALYSIS_DIR / "dupes_ignored.json"
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("ignored") or [])
    except Exception:
        return set()

def _write_ignored(s: set[str]) -> None:
    p = settings.ANALYSIS_DIR / "dupes_ignored.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"ignored": sorted(s)}, indent=2), encoding="utf-8")

def _group_key(ids):
    return ",".join(sorted(ids))

def dedup_review(request):
    groups = _read_dupes()
    ignored = _ignored_set()
    show_all = request.GET.get("all") == "1"
    vis_groups = []
    for g in groups:
        key = _group_key(g)
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
            rows.append({
                "id": str(c.id),
                "title": c.title or "(Untitled)",
                "doi": c.doi or "",
                "year": c.year or "",
                "journal": _journal_full(c.meta or {}, c.csl or {}),
            })
        if len(rows) > 1:
            decorated.append(rows)

    return render(request, "captures/dupes.html", {
        "groups": decorated,
        "ignored_count": len(ignored),
        "all_mode": show_all,
    })

@require_POST
def dedup_scan_view(_request):
    from captures.dedup import find_near_duplicates
    groups = find_near_duplicates(threshold=0.85)
    p = settings.ANALYSIS_DIR / "dupes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"groups": groups}, indent=2), "utf-8")
    return redirect("dedup_review")

@require_POST
def dedup_ignore(request):
    ids = request.POST.getlist("ids")
    if not ids:
        return redirect("dedup_review")
    ignored = _ignored_set()
    ignored.add(_group_key(ids))
    _write_ignored(ignored)
    return redirect("dedup_review")

@require_POST
def dedup_merge(request):
    primary_id = request.POST.get("primary")
    others = request.POST.getlist("others")
    if not primary_id or not others:
        return redirect("dedup_review")

    primary = get_object_or_404(Capture, pk=primary_id)
    from django.conf import settings as _s
    # transactional merge
    with transaction.atomic():
        for oid in others:
            if oid == primary_id:
                continue
            dup = Capture.objects.filter(pk=oid).first()
            if not dup:
                continue
            # move refs
            Reference.objects.filter(capture_id=dup.id).update(capture=primary)
            # move collections
            for col in dup.collections.all():
                col.captures.add(primary)
            # delete dup
            dup.delete()
            # remove dup artifacts folder
            try:
                shutil.rmtree((_s.ARTIFACTS_DIR / str(oid)), ignore_errors=True)
            except Exception:
                pass

    # mark this group as handled
    ignored = _ignored_set()
    ids = [primary_id] + others
    ignored.add(_group_key(ids))
    _write_ignored(ignored)

    return redirect("dedup_review")
