# services/server/captures/views/common.py
from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from typing import Any, TypedDict
from urllib.parse import urlparse

from django.core.cache import cache
from django.db.models import Count

from captures.models import Capture, Collection
from captures.reduced_view import read_reduced_view
from captures.keywords import split_keywords
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


def _author_list(meta: dict, csl: dict) -> list[str]:
    names: list[str] = []
    if isinstance(meta, dict) and isinstance(meta.get("authors"), list):
        for a in meta["authors"]:
            if isinstance(a, str) and a.strip():
                names.append(a.strip())
            elif isinstance(a, dict):
                fam = (a.get("family") or a.get("last") or "").strip()
                giv = (a.get("given") or a.get("first") or "").strip()
                names.append(" ".join([t for t in (giv, fam) if t]))
    if isinstance(csl, dict) and isinstance(csl.get("author"), list):
        for a in csl["author"]:
            fam = (a.get("family") or a.get("last") or "").strip()
            giv = (a.get("given") or a.get("first") or "").strip()
            names.append(" ".join([t for t in (giv, fam) if t]))
    seen, out = set(), []
    for n in names:
        key = n.lower()
        if n and key not in seen:
            seen.add(key)
            out.append(n)
    return out


def _authors_intext(meta: dict, csl: dict) -> str:
    raw = _author_list(meta or {}, csl or {})
    if not raw:
        return ""
    fam = _family_from_name(raw[0])
    return fam if len(raw) == 1 else f"{fam} et al."


def _journal_full(meta: dict, csl: dict) -> str:
    meta = meta or {}
    csl = csl or {}
    return (
        meta.get("container_title")
        or meta.get("container-title")
        or meta.get("journal")
        or csl.get("container-title")
        or csl.get("container_title")
        or ""
    )


def _doi_url(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi if doi.startswith("http://") or doi.startswith("https://") else f"https://doi.org/{doi}"


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

    try:
        refs_count = c.references.count()  # dynamic related manager (safe at runtime)
    except Exception:
        refs_count = 0

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
    Normalizes journal & site query params to lowercase before comparing.
    Prefers the persisted Capture.site host for site filtering.
    """
    j_key = (journal or "").strip().lower()
    s_key = (site or "").strip().lower()
    y_key = (year or "").strip()

    out: list[Capture] = []
    for c in qs:
        meta = c.meta or {}
        csl = c.csl or {}
        # Year: match persisted or common meta fallbacks used by _row
        year_val = str(c.year or meta.get("year") or meta.get("publication_year") or "")
        year_ok = (not y_key) or (year_val == y_key)
        # Journal
        j = _journal_full(meta, csl).lower()
        journal_ok = (not j_key) or (j == j_key)
        # Site
        site_src = (c.site or "").replace("www.", "") or _site_label(c.url or "")
        site_ok = (not s_key) or (site_src.lower() == s_key)
        # Collection (via safe helper to satisfy Pylance)
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
    "_abstract_from_view",
    "_row",
    "_apply_filters",
    "_build_facets",
    "_collections_with_counts",
]
