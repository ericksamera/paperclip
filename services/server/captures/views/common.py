# services/server/captures/views/common.py
from __future__ import annotations
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

from django.db.models import Count
from django.core.cache import cache

from captures.models import Capture, Collection
from paperclip.journals import get_short_journal_name
from captures.reduced_view import read_reduced_view


def _site_label(url: str) -> str:
    """
    Prefer host persisted on the Capture.site field when present (set at ingest),
    otherwise derive from URL.
    """
    try:
        host = urlparse(url).hostname or ""
        return host.replace("www.", "") if host else ""
    except Exception:
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


def _author_list(meta: dict, csl: dict) -> List[str]:
    names: List[str] = []
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
    meta = meta or {}; csl = csl or {}
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


# ---------- Pull abstract from reduced view (with preview fallback) ----------
def _abstract_from_view(c: Capture, preview_max_paras: int = 3) -> str:
    """
    Prefer the 'abstract' we persist in the reduced view; fall back to a short
    preview constructed from the first few 'abstract_or_body' paragraphs.

    Reads via read_reduced_view(...) which tolerates historical filenames
    ('view.json', 'server_output_reduced.json', 'parsed.json').
    """
    try:
        view = read_reduced_view(str(c.id)) or {}
        sections = view.get("sections") or {}
        if not isinstance(sections, dict):
            return ""
        abs_txt = sections.get("abstract")
        if isinstance(abs_txt, str) and abs_txt.strip():
            return abs_txt.strip()

        paras = sections.get("abstract_or_body")
        if isinstance(paras, list) and paras:
            # join a short preview
            return " ".join([str(p) for p in paras[:preview_max_paras] if p]).strip()
    except Exception:
        pass
    return ""


def _row(c: Capture) -> Dict[str, Any]:
    meta = c.meta or {}
    csl = c.csl or {}

    title = (c.title or meta.get("title") or csl.get("title") or c.url or "").strip() or "(Untitled)"
    authors_intext = _authors_intext(meta, csl)
    j_full = _journal_full(meta, csl)
    j_short = get_short_journal_name(j_full, csl)
    doi = (c.doi or meta.get("doi") or csl.get("DOI") or "").strip()
    keywords = meta.get("keywords") or []

    # Prefer reduced view abstract; fall back to meta/csl
    abstract = _abstract_from_view(c) or (meta.get("abstract") or (csl.get("abstract") if isinstance(csl, dict) else "") or "")

    try:
        refs_count = c.references.count()
    except Exception:
        refs_count = 0

    # Prefer normalized host field if present; else derive from URL
    site_lbl = (c.site or "").replace("www.", "") if (getattr(c, "site", "") or "") else _site_label(c.url or "")

    return {
        "id": str(c.id),
        "title": title,
        "url": c.url or "",
        "site_label": site_lbl,
        "authors_intext": authors_intext,
        "journal": j_full,
        "journal_short": j_short or j_full,
        "year": c.year or meta.get("year") or meta.get("publication_year") or "",
        "doi": doi,
        "doi_url": _doi_url(doi) or "",
        "keywords": keywords,
        "abstract": abstract,
        "added": c.created_at.strftime("%Y-%m-%d"),
        "refs": refs_count,
    }


def _apply_filters(qs: Iterable[Capture], *, year: str, journal: str, site: str, col: str) -> List[Capture]:
    """
    Stable, case-insensitive filtering over year / journal / site / collection.
    Normalizes journal & site query params to lowercase before comparing.
    Prefers the persisted Capture.site host for site filtering (added in migration 0003).
    """
    j_key = (journal or "").strip().lower()
    s_key = (site or "").strip().lower()
    y_key = (year or "").strip()

    out: List[Capture] = []
    for c in qs:
        meta = c.meta or {}; csl = c.csl or {}

        # Year: match persisted or common meta fallbacks used by _row
        year_val = str(c.year or meta.get("year") or meta.get("publication_year") or "")
        year_ok = (not y_key) or (year_val == y_key)

        # Journal
        j = _journal_full(meta, csl).lower()
        journal_ok = (not j_key) or (j == j_key)

        # Site: prefer normalized persisted host, then fallback to deriving from URL
        site_src = (c.site or "").replace("www.", "") or _site_label(c.url or "")
        site_ok = (not s_key) or (site_src.lower() == s_key)

        # Collection
        col_ok = True
        if col:
            col_ok = c.collections.filter(id=col).exists()

        if year_ok and journal_ok and site_ok and col_ok:
            out.append(c)
    return out


def _build_facets(all_caps: Iterable[Capture]) -> Dict[str, Any]:
    """
    Build years/journals/sites facets with a short TTL cache.
    Auto-invalidated by captures.app on save/delete.
    """
    KEY = "facets:all"
    cached = cache.get(KEY)
    if cached:
        return cached

    years: Dict[str, int] = {}
    journals: Dict[str, int] = {}
    sites: Dict[str, int] = {}

    # Iterate with only fields we actually need (cheap on SQLite)
    for c in all_caps.only("year", "url", "meta", "csl", "site"):
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

    yr_sorted = sorted(years.items(), key=lambda kv: int(kv[0]), reverse=True)  # type: ignore[index]
    max_count = (max(years.values()) if years else 1)
    years_hist = [{"label": y, "count": n, "pct": int(round(n * 100 / max_count))} for y, n in yr_sorted]

    def sort_desc(d: Dict[str, int]) -> List[tuple[str, int]]:
        return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))

    out = {"years": years_hist, "journals": sort_desc(journals), "sites": sort_desc(sites)}
    cache.set(KEY, out, timeout=90)  # 90s is plenty; change anytime
    return out


def _collections_with_counts() -> List[Dict[str, Any]]:
    cols = Collection.objects.annotate(count=Count("captures")).order_by("name")
    return [{"id": c.id, "name": c.name, "count": c.count, "parent": c.parent_id} for c in cols]
