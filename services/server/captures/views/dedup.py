from __future__ import annotations
import json, re, shutil

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from captures.models import Capture, Reference
from captures.reduced_view import read_reduced_view

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


def _preview_for(c: Capture) -> str:
    """
    Small, stable preview for the dedup table:
      1) Prefer reduced view -> sections.abstract_or_body (first 1–3 paras)
      2) Fallback to meta.abstract or csl.abstract
    """
    try:
        view = read_reduced_view(str(c.id))
        paras = ((view.get("sections") or {}).get("abstract_or_body") or [])
        txt = " ".join((paras[:3] or []))
        if txt:
            import re as _re
            txt = _re.sub(r"\s+", " ", txt).strip()
            return (txt[:280] + "…") if len(txt) > 280 else txt
    except Exception:
        pass

    meta = c.meta or {}; csl = c.csl or {}
    txt = (meta.get("abstract") or csl.get("abstract") or "").strip()
    if txt:
        import re as _re
        txt = _re.sub(r"\s+", " ", txt)
        return (txt[:280] + "…") if len(txt) > 280 else txt
    return ""


def _format_added(dt):
    """
    Return (human_str, iso_str) for the Added column.
    human_str example: '2025-09-29 14:07 PDT'
    iso_str example:   '2025-09-29T14:07-07:00'
    """
    if not dt:
        return "", ""
    try:
        dt_local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    except Exception:
        dt_local = dt
    human = dt_local.strftime("%Y-%m-%d %H:%M")
    tzname = dt_local.tzname() or ""
    if tzname:
        human = f"{human} {tzname}"
    # minutes precision keeps the cell compact but precise
    try:
        iso = dt_local.isoformat(timespec="minutes")
    except TypeError:
        # Python < 3.6 fallback (not expected, but safe)
        iso = dt_local.replace(second=0, microsecond=0).isoformat()
    return human, iso


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
            added_h, added_iso = _format_added(c.created_at)
            rows.append({
                "id": str(c.id),
                "title": c.title or "(Untitled)",
                "doi": c.doi or "",
                "year": c.year or "",
                "journal": _journal_full(c.meta or {}, c.csl or {}),
                "added": added_h,
                "added_iso": added_iso,
                "preview": _preview_for(c),
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
