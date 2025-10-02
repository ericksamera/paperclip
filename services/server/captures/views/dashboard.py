from __future__ import annotations
from typing import Any, Dict, Iterable, List, Tuple

from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, render

from captures.models import Capture, Collection
from .common import _author_list, _journal_full, _site_label, _family_from_name


def _year_of(c: Capture) -> str:
    meta = c.meta or {}
    csl = c.csl or {}
    # Mirrors _apply_filters/_row year logic
    val = c.year or meta.get("year") or meta.get("publication_year") or ""
    try:
        return str(int(val))
    except Exception:
        return str(val or "")


def _tally(items: Iterable[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for it in items:
        key = (it or "").strip()
        if not key:
            continue
        out[key] = out.get(key, 0) + 1
    return out


def _topn(d: Dict[str, int], n: int = 12) -> List[Tuple[str, int]]:
    return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def _facets_for_caps(caps: Iterable[Capture]) -> Dict[str, Any]:
    years: Dict[str, int] = {}
    journals: Dict[str, int] = {}
    sites: Dict[str, int] = {}
    authors: Dict[str, int] = {}

    for c in caps:
        # Year
        y = _year_of(c)
        if y:
            years[y] = years.get(y, 0) + 1

        # Journal
        j = _journal_full(c.meta or {}, c.csl or {})
        if j:
            journals[j] = journals.get(j, 0) + 1

        # Sites — prefer persisted host, else derive from URL
        host = (c.site or "").replace("www.", "") or _site_label(c.url or "")
        if host:
            sites[host] = sites.get(host, 0) + 1

        # Authors — count by **family** name to keep bins compact
        for name in _author_list(c.meta or {}, c.csl or {}):
            fam = _family_from_name(name)
            if fam:
                authors[fam] = authors.get(fam, 0) + 1

    # Years → normalized histogram for UI bars
    yr_sorted = sorted(years.items(), key=lambda kv: int(kv[0]), reverse=True) if years else []
    max_count = max(years.values()) if years else 1
    years_hist = [{"label": y, "count": n, "pct": int(round(n * 100 / max_count))} for y, n in yr_sorted]

    return {
        "years": years_hist,
        "journals": _topn(journals, 12),
        "sites": _topn(sites, 12),
        "authors": _topn(authors, 12),
        "years_stats": {
            "min": int(min((int(y) for y, _ in yr_sorted), default=0)) if yr_sorted else None,
            "max": int(max((int(y) for y, _ in yr_sorted), default=0)) if yr_sorted else None,
            "mode": int(yr_sorted[0][0]) if yr_sorted else None,
            "span": (int(max((int(y) for y, _ in yr_sorted), default=0)) - int(min((int(y) for y, _ in yr_sorted), default=0))) if len(yr_sorted) >= 2 else (0 if yr_sorted else None),
        },
    }


def collection_dashboard(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    return render(request, "captures/collection_dashboard.html", {"collection": col})


def collection_summary_json(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    caps = list(col.captures.all())  # tiny, safe read; add pagination if it grows huge
    facets = _facets_for_caps(caps)
    data = {
        "ok": True,
        "collection": {"id": col.id, "name": col.name, "count": len(caps)},
        **facets,
    }
    return JsonResponse(data)
