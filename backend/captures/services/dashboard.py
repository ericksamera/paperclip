from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from captures.models import Capture, Collection
from captures.views.common import (
    _author_list,
    _family_from_name,
    _journal_full,
    _site_label,
)


def _year_of(c: Capture) -> str:
    """
    Normalize a capture's year the same way Library filters/rows do.
    """
    meta = c.meta or {}
    val = c.year or meta.get("year") or meta.get("publication_year") or ""
    try:
        return str(int(val))
    except Exception:
        return str(val or "")


def _tally(items: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        key = (it or "").strip()
        if not key:
            continue
        out[key] = out.get(key, 0) + 1
    return out


def _topn(d: dict[str, int], n: int = 12) -> list[tuple[str, int]]:
    return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def facets_for_caps(caps: Iterable[Capture]) -> dict[str, Any]:
    """
    Compute year/journal/site/author facets for an iterable of captures.

    Returns a dict with:
      - years: [{label, count, pct}]
      - journals: [(name, count)...]
      - sites: [(host, count)...]
      - authors: [(family_name, count)...]
      - years_stats: {min, max, mode, span}
    """
    years: dict[str, int] = {}
    journals: dict[str, int] = {}
    sites: dict[str, int] = {}
    authors: dict[str, int] = {}

    for c in caps:
        # Year
        y = _year_of(c)
        if y:
            years[y] = years.get(y, 0) + 1

        # Journal
        j = _journal_full(c.meta or {}, c.csl or {})
        if j:
            journals[j] = journals.get(j, 0) + 1

        # Site/host (prefer persisted host, else derive from URL)
        host = (c.site or "").replace("www.", "") or _site_label(c.url or "")
        if host:
            sites[host] = sites.get(host, 0) + 1

        # Authors (family names) to keep bins compact
        for name in _author_list(c.meta or {}, c.csl or {}):
            fam = _family_from_name(name)
            if fam:
                authors[fam] = authors.get(fam, 0) + 1

    # Years histogram
    yr_sorted = (
        sorted(years.items(), key=lambda kv: int(kv[0]), reverse=True) if years else []
    )
    max_count = max(years.values()) if years else 1
    years_hist = [
        {"label": y, "count": n, "pct": round(n * 100 / max_count)}
        for y, n in yr_sorted
    ]

    years_stats: dict[str, Any] = {"min": None, "max": None, "mode": None, "span": None}
    if yr_sorted:
        ys = [int(y) for y, _ in yr_sorted]
        years_stats["min"] = min(ys)
        years_stats["max"] = max(ys)
        years_stats["mode"] = int(yr_sorted[0][0])
        years_stats["span"] = (
            years_stats["max"] - years_stats["min"] if len(ys) >= 2 else 0
        )

    return {
        "years": years_hist,
        "journals": _topn(journals, 12),
        "sites": _topn(sites, 12),
        "authors": _topn(authors, 12),
        "years_stats": years_stats,
    }


def facets_for_collection(col: Collection) -> dict[str, Any]:
    """
    Convenience wrapper: facets for all captures in a collection.
    """
    caps = col.captures.all()
    return facets_for_caps(caps)
