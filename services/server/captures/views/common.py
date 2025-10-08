# services/server/captures/views/common.py
from __future__ import annotations

import re

from collections.abc import Iterable
from contextlib import suppress
from typing import Any, Mapping, TypedDict, cast
from urllib.parse import urlparse

from django.core.cache import cache
from django.db.models import Count

from captures.models import Capture, Collection
from captures.reduced_view import read_reduced_view
from captures.keywords import split_keywords
from captures.types import CSL  # typed CSL view
from paperclip.journals import get_short_journal_name


# =========================
# Typed structures
# =========================
class YearBucket(TypedDict):
    label: str
    count: int
    pct: int


class Facets(TypedDict):
    years: list[YearBucket]
    journals: list[tuple[str, int]]
    sites: list[tuple[str, int]]


class LibraryRow(TypedDict):
    id: str
    title: str
    url: str
    site_label: str
    authors_intext: str
    journal: str
    journal_short: str
    year: str
    doi: str
    doi_url: str
    keywords: list[str]
    abstract: str
    added: str
    refs: int


class CollectionSummary(TypedDict):
    id: int
    name: str
    count: int
    parent: int | None


# =========================
# Small helpers
# =========================
def _site_label(url: str) -> str:
    """
    Prefer host persisted on the Capture.site field when present (set at ingest),
    otherwise derive from URL.
    """
    with suppress(Exception):
        host = urlparse(url).hostname or ""
        return host.replace("www.", "") if host else ""
    return ""


def _family_from_name(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if "," in s:
        fam = s.split(",", 1)[0].strip()
        return fam or s
    parts = [p for p in s.replace("·", " ").split() if p]
    return parts[-1] if parts else s


def _norm_str_or_first(v: Any) -> str:
    """
    Normalize a meta/CSL field into a clean str.
    Accepts str | list[str] | Any; returns '' for falsy values.
    """
    if isinstance(v, list):
        # prefer first non-empty string, else first item stringified
        for s in v:
            if isinstance(s, str) and s.strip():
                return s.strip()
        return str(v[0]).strip() if v else ""
    return ("" if v is None else str(v)).strip()


def _author_list(meta: Mapping[str, Any], csl: CSL | Mapping[str, Any]) -> list[str]:
    """
    Return ["Given Family", ...] using CSL authors when present; fallback to meta.authors.
    """
    names: list[str] = []

    # Prefer CSL
    try:
        csl_auth = (csl or {}).get("author")  # type: ignore[index]
    except Exception:
        csl_auth = None
    if isinstance(csl_auth, list):
        for a in csl_auth:
            if isinstance(a, dict):
                fam = (a.get("family") or a.get("last") or "").strip()
                giv = (a.get("given") or a.get("first") or "").strip()
                full = " ".join([t for t in (giv, fam) if t]).strip()
                if full:
                    names.append(full)

    # Fallback: meta.authors (strings or dicts)
    if not names and isinstance(meta, Mapping) and isinstance(meta.get("authors"), list):
        for a in meta["authors"]:
            if isinstance(a, str) and a.strip():
                names.append(a.strip())
            elif isinstance(a, dict):
                fam = (a.get("family") or a.get("last") or "").strip()
                giv = (a.get("given") or a.get("first") or "").strip()
                full = " ".join([t for t in (giv, fam) if t]).strip()
                if full:
                    names.append(full)

    # De-dup while keeping order
    seen, out = set(), []
    for n in names:
        key = n.lower()
        if n and key not in seen:
            seen.add(key)
            out.append(n)
    return out


def _authors_intext(meta: Mapping[str, Any], csl: CSL | Mapping[str, Any]) -> str:
    raw = _author_list(meta or {}, csl or {})
    if not raw:
        return ""
    fam = _family_from_name(raw[0])
    return fam if len(raw) == 1 else f"{fam} et al."


def _journal_full(meta: Mapping[str, Any], csl: CSL | Mapping[str, Any]) -> str:
    """
    Resolve the "container title" robustly from meta or CSL.
    Always returns a string to satisfy Pylance/mypy.
    """
    csl_map: Mapping[str, Any] = csl if isinstance(csl, Mapping) else {}
    return (
        _norm_str_or_first(meta.get("container_title"))
        or _norm_str_or_first(meta.get("container-title"))
        or _norm_str_or_first(meta.get("journal"))
        or _norm_str_or_first(csl_map.get("container-title"))
        or _norm_str_or_first(csl_map.get("container_title"))
        or ""
    )


def _doi_url(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi if doi.startswith("http://") or doi.startswith("https://") else f"https://doi.org/{doi}"


# ---------- references helpers (Pylance-safe) ----------
def _ref_count(c: Capture) -> int:
    """
    Return count of related references without touching the dynamic attribute
    at type-check time (keeps Pylance quiet).
    """
    mgr = cast(Any, getattr(c, "references", None))
    try:
        return int(mgr.count())
    except Exception:
        return 0


def _references_ordered(c: Capture):
    """
    Return an iterable for templates: references ordered by id, or [].
    """
    mgr = cast(Any, getattr(c, "references", None))
    try:
        return mgr.all().order_by("id")
    except Exception:
        return []


# ---------- Abstract (reduced view preferred) ----------
def _abstract_from_view(c: Capture, preview_max_paras: int = 3) -> str:
    """
    Prefer the 'abstract' we persist in the reduced view; fall back to a short
    preview constructed from the first few 'abstract_or_body' paragraphs.
    """
    view = read_reduced_view(str(c.id)) or {}
    sections = view.get("sections") or {}
    if not isinstance(sections, dict):
        return ""
    abs_txt = sections.get("abstract")
    if isinstance(abs_txt, str) and abs_txt.strip():
        return abs_txt.strip()
    paras = sections.get("abstract_or_body")
    if isinstance(paras, list) and paras:
        return " ".join([str(p) for p in paras[:preview_max_paras] if p]).strip()
    return ""


def _row(c: Capture) -> LibraryRow:
    meta = c.meta or {}
    csl = c.csl or {}
    title = (c.title or meta.get("title") or csl.get("title") or c.url or "").strip() or "(Untitled)"
    authors_intext = _authors_intext(meta, csl)
    j_full = _journal_full(meta, csl)
    j_short = get_short_journal_name(j_full, csl) or j_full
    doi_raw = (c.doi or meta.get("doi") or (csl.get("DOI") if isinstance(csl, dict) else "") or "").strip()

    # Keywords → always list[str]
    kw_in = meta.get("keywords") or []
    if isinstance(kw_in, str):
        keywords = split_keywords(kw_in)
    elif isinstance(kw_in, list):
        keywords = [str(k) for k in kw_in if k]
    else:
        keywords = []

    # Abstract (reduced view preferred; fall back to meta/csl)
    abstract = _abstract_from_view(c) or (
        meta.get("abstract") or (csl.get("abstract") if isinstance(csl, dict) else "") or ""
    )

    refs_count = _ref_count(c)

    # Prefer normalized host field if present; else derive from URL
    site_lbl = ((c.site or "").replace("www.", "")) if (getattr(c, "site", "") or "") else _site_label(c.url or "")

    return LibraryRow(
        id=str(c.id),
        title=title,
        url=c.url or "",
        site_label=site_lbl,
        authors_intext=authors_intext,
        journal=j_full,
        journal_short=j_short,
        year=str(c.year or meta.get("year") or meta.get("publication_year") or ""),
        doi=doi_raw,
        doi_url=_doi_url(doi_raw) or "",
        keywords=keywords,
        abstract=abstract,
        added=c.created_at.strftime("%Y-%m-%d"),
        refs=int(refs_count),
    )


def _in_collection(c: Capture, col_id: str) -> bool:
    """
    Pylance-safe membership check. We access the ManyToMany reverse-manager via getattr
    so static checkers (that don't run the Django plugin) don't complain.
    """
    if not col_id:
        return True
    try:
        mgr: Any = getattr(c, "collections", None)  # ManyRelatedManager at runtime
        if mgr is None:
            return False
        # mgr.filter(...).exists()
        q = getattr(mgr, "filter", lambda **kw: None)(id=col_id)
        if q is None:
            return False
        exists = getattr(q, "exists", lambda: False)
        return bool(exists())
    except Exception:
        return False


def _apply_filters(
    qs: Iterable[Capture], *, year: str, journal: str, site: str, col: str
) -> list[Capture]:
    """
    Stable, case-insensitive filtering over year / journal / site / collection.
    Supports:
      - year exact: "2018"
      - closed range: "2010-2020" or "2010:2020"
      - open high:  ">=2015" or "2015+"
      - open low:   "<=2012"
    """
    def _parse_year_range(expr: str) -> tuple[int | None, int | None] | None:
        expr = (expr or "").strip()
        if not expr:
            return None
        m = re.match(r"^\s*(\d{4})\s*[-:]\s*(\d{4})\s*$", expr)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return (min(a, b), max(a, b))
        m = re.match(r"^\s*>=?\s*(\d{4})\s*$", expr) or re.match(r"^\s*(\d{4})\+\s*$", expr)
        if m:
            return (int(m.group(1)), None)
        m = re.match(r"^\s*<=?\s*(\d{4})\s*$", expr)
        if m:
            return (None, int(m.group(1)))
        m = re.match(r"^\s*(\d{4})\s*$", expr)
        if m:
            y = int(m.group(1))
            return (y, y)
        return None

    j_key = (journal or "").strip().lower()
    s_key = (site or "").strip().lower()
    yr_key = (year or "").strip()
    yr_span = _parse_year_range(yr_key)

    out: list[Capture] = []
    for c in qs:
        meta = c.meta or {}
        csl = c.csl or {}
        # ---- YEAR ----
        yraw = c.year or meta.get("year") or meta.get("publication_year")
        try:
            yval = int(str(yraw)) if (yraw is not None and str(yraw).strip()) else None
        except Exception:
            yval = None
        if yr_span is None:
            year_ok = True
        else:
            lo, hi = yr_span
            if yval is None:
                year_ok = False
            elif lo is not None and yval < lo:
                year_ok = False
            elif hi is not None and yval > hi:
                year_ok = False
            else:
                year_ok = True

        # ---- JOURNAL ----
        j = _journal_full(meta, csl).lower()
        journal_ok = (not j_key) or (j == j_key)

        # ---- SITE ----
        site_src = (c.site or "").replace("www.", "") or _site_label(c.url or "")
        site_ok = (not s_key) or (site_src.lower() == s_key)

        # ---- COLLECTION ----
        col_ok = True if not col else _in_collection(c, col)

        if year_ok and journal_ok and site_ok and col_ok:
            out.append(c)
    return out


def _build_facets(all_caps: Iterable[Capture]) -> Facets:
    """
    Build years/journals/sites facets with a short TTL cache.
    Auto-invalidated by captures.app on save/delete.
    """
    KEY = "facets:all"
    cached = cache.get(KEY)
    if cached:
        # Trust cached type
        return cached  # type: ignore[return-value]

    years: dict[str, int] = {}
    journals: dict[str, int] = {}
    sites: dict[str, int] = {}

    # Iterate with only fields we actually need (cheap on SQLite) if supported.
    qs_iter: Iterable[Capture] = all_caps
    try:
        only = getattr(all_caps, "only", None)
        if callable(only):
            # type: ignore[misc,call-arg]
            qs_iter = only("year", "url", "meta", "csl", "site")
    except Exception:
        qs_iter = all_caps

    for c in qs_iter:
        if c.year:
            key = str(c.year)
            years[key] = years.get(key, 0) + 1
        j = _journal_full(c.meta or {}, c.csl or {})
        if j:
            journals[j] = journals.get(j, 0) + 1
        # Prefer normalized host field
        site = (c.site or "").replace("www.", "") if (c.site or "") else _site_label(c.url or "")
        if site:
            sites[site] = sites.get(site, 0) + 1

    yr_sorted = sorted(((str(y), n) for y, n in years.items()), key=lambda kv: int(kv[0]), reverse=True)
    max_count = max(years.values()) if years else 1
    years_hist: list[YearBucket] = [
        {"label": y, "count": n, "pct": int(round(n * 100 / max_count))} for y, n in yr_sorted
    ]

    def sort_desc(d: dict[str, int]) -> list[tuple[str, int]]:
        return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))

    out: Facets = {"years": years_hist, "journals": sort_desc(journals), "sites": sort_desc(sites)}
    cache.set(KEY, out, timeout=90)
    return out


def _collections_with_counts() -> list[CollectionSummary]:
    cols = Collection.objects.annotate(count=Count("captures")).order_by("name")
    return [{"id": c.id, "name": c.name, "count": c.count, "parent": c.parent_id} for c in cols]


__all__ = [
    "_site_label",
    "_family_from_name",
    "_author_list",
    "_authors_intext",
    "_journal_full",
    "_doi_url",
    "_ref_count",
    "_references_ordered",
    "_abstract_from_view",
    "_row",
    "_apply_filters",
    "_build_facets",
    "_collections_with_counts",
]
