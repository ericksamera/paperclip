# services/server/captures/views/library.py
from __future__ import annotations
from typing import List, Dict, Tuple, Any

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from captures.models import Capture
from captures.search import search_ids
from .common import (
    _row,
    _apply_filters,
    _build_facets,
    _collections_with_counts,
    _authors_intext,
    _journal_full,
)

# ------------------------ helpers (shared by both endpoints) ------------------------

def _search_ids_for_query(qterm: str, search_mode: str) -> List[str]:
    """
    Returns a ranked list of capture IDs for the given query, honoring:
      • 'semantic' mode
      • 'hybrid' mode
      • '~query' shortcut for semantic
    Falls back to FTS on any embedding/index error.
    """
    qterm = (qterm or "").strip()
    use_sem = (search_mode == "semantic") or (qterm.startswith("~") and len(qterm) > 1)
    use_hybrid = (search_mode == "hybrid")
    if not (use_sem or use_hybrid):
        return search_ids(qterm)
    qraw = qterm[1:].strip() if qterm.startswith("~") else qterm
    try:
        if use_sem:
            from captures.semantic import search_ids_semantic
            return search_ids_semantic(qraw, k=2000)
        from captures.semantic import rrf_hybrid_ids
        return rrf_hybrid_ids(qraw, limit=2000)
    except Exception:
        return search_ids(qraw)


def _filter_and_rank(ids: List[str], *, year: str, journal: str, site: str, col: str) -> Tuple[List[Capture], Dict[str, int]]:
    """Filter the subset of Capture rows in ids and return (ordered_list, rank_map)."""
    rank = {pk: i for i, pk in enumerate(ids)}
    qs = Capture.objects.filter(id__in=ids)
    filtered: List[Capture] = _apply_filters(qs, year=year, journal=journal, site=site, col=col)
    filtered.sort(key=lambda c: rank.get(str(c.id), 10**9))
    return filtered, rank


def _sort_key(c: Capture, key: str) -> Any:
    """
    Compute sort keys matching what the UI shows:
      - title: case-insensitive
      - authors: first family name or 'X et al.' via _authors_intext(...)
      - year: integer (unknown → 0)
      - journal: full container title (case-insensitive)
      - created_at/added: datetime
      - refs: integer (count of references)
      - doi: normalized string
    """
    meta = c.meta or {}
    csl = c.csl or {}

    k = (key or "").lower()
    if k in ("added", "created_at"):
        return c.created_at
    if k == "title":
        t = (c.title or meta.get("title") or csl.get("title") or c.url or "")
        return str(t).casefold()
    if k == "authors":
        return _authors_intext(meta, csl).casefold()
    if k == "year":
        y = c.year or meta.get("year") or meta.get("publication_year")
        try:
            return int(str(y))
        except Exception:
            return 0
    if k == "journal":
        return _journal_full(meta, csl).casefold()
    if k == "refs":
        try:
            return int(c.references.count())
        except Exception:
            return 0
    if k == "doi":
        d = (c.doi or meta.get("doi") or (csl.get("DOI") if isinstance(csl, dict) else "") or "")
        return str(d).casefold()
    # Fallback = added
    return c.created_at


def _maybe_sort(caps: List[Capture], *, qterm: str, sort: str | None, direction: str | None) -> List[Capture]:
    """
    Sorts only when requested. For search mode (qterm present) we default to 'rank'
    (keep the relevance order) unless a sort key is explicitly provided.
    """
    # Default behavior:
    # - When searching and sort is missing -> keep rank order (no resort).
    # - When not searching and sort is missing -> default to 'created_at' DESC.
    if qterm:
        effective_sort = (sort or "rank").lower()
        if effective_sort == "rank":
            return caps  # keep the relevance order computed earlier
    else:
        effective_sort = (sort or "created_at").lower()

    reverse = (str(direction or "").lower() == "desc")
    caps.sort(key=lambda c: _sort_key(c, effective_sort), reverse=reverse)
    return caps

# ------------------------ views ------------------------

class LibraryView(View):
    template_name = "captures/list.html"

    def get(self, request):
        # Read request params
        sort = request.GET.get("sort")          # None means defaulting logic applies
        direction = request.GET.get("dir", "desc")
        qterm = (request.GET.get("q") or "").strip()
        search_mode = (request.GET.get("search") or "").strip().lower()  # 'semantic' | 'hybrid' | ''
        year = (request.GET.get("year") or "").strip()
        journal = (request.GET.get("journal") or "").strip()
        site = (request.GET.get("site") or "").strip()
        col = (request.GET.get("col") or "").strip()
        per = int(request.GET.get("per") or 200)
        page_no = int(request.GET.get("page") or 1)

        base_qs = Capture.objects.all().order_by("-created_at")
        facets = _build_facets(base_qs)
        collections = _collections_with_counts()

        selected = {"q": qterm, "year": year, "journal": journal, "site": site, "col": col, "search": search_mode}

        if qterm:
            # Searching: get ranked IDs then optionally resort if user clicked a header
            ids = _search_ids_for_query(qterm, search_mode)
            filtered, _rank = _filter_and_rank(ids, year=year, journal=journal, site=site, col=col)
            filtered = _maybe_sort(filtered, qterm=qterm, sort=sort, direction=direction)
            total = len(filtered)
            start = (page_no - 1) * per
            end = start + per
            rows = [_row(c) for c in filtered[start:end]]

            # “All items” count for the Collections header when a search is active
            all_items_filtered = _apply_filters(Capture.objects.filter(id__in=ids), year=year, journal=journal, site=site, col="")
            collections_all_count = len(all_items_filtered)

            # Expose current params so qs_sort can generate toggles
            current_params = request.GET

            # For UI arrows: if user didn't choose a sort, we surface 'rank' so no arrow is highlighted
            ui_sort = sort or "rank"

            return render(
                request,
                self.template_name,
                {
                    "rows": rows,
                    "count": total,
                    "sort": ui_sort,
                    "dir": direction,
                    "current_params": current_params,
                    "selected": selected,
                    "facets": facets,
                    "collections": collections,
                    "collections_all_count": collections_all_count,
                },
            )

        # Non-search listing (simple ordering + pagination)
        filtered = _apply_filters(base_qs, year=year, journal=journal, site=site, col=col)
        filtered = _maybe_sort(filtered, qterm="", sort=sort, direction=direction)
        paginator = Paginator(filtered, per)
        page = paginator.get_page(page_no)
        rows = [_row(c) for c in page.object_list]
        all_items_filtered = _apply_filters(base_qs, year=year, journal=journal, site=site, col="")
        collections_all_count = len(all_items_filtered)

        current_params = request.GET
        ui_sort = (sort or "created_at")

        return render(
            request,
            self.template_name,
            {
                "rows": rows,
                "count": paginator.count,
                "sort": ui_sort,
                "dir": direction,
                "current_params": current_params,
                "selected": selected,
                "facets": facets,
                "collections": collections,
                "collections_all_count": collections_all_count,
            },
        )


def library_page(request):
    per = int(request.GET.get("per") or 200)
    page_no = int(request.GET.get("page") or 1)
    qterm = (request.GET.get("q") or "").strip()
    search_mode = (request.GET.get("search") or "").strip().lower()
    year = (request.GET.get("year") or "").strip()
    journal = (request.GET.get("journal") or "").strip()
    site = (request.GET.get("site") or "").strip()
    col = (request.GET.get("col") or "").strip()
    sort = request.GET.get("sort")           # same semantics as full page
    direction = request.GET.get("dir", "desc")

    if qterm:
        ids = _search_ids_for_query(qterm, search_mode)
        filtered, _rank = _filter_and_rank(ids, year=year, journal=journal, site=site, col=col)
        filtered = _maybe_sort(filtered, qterm=qterm, sort=sort, direction=direction)
        paginator = Paginator(filtered, per)
        page = paginator.get_page(page_no)
        rows = [_row(c) for c in page.object_list]
        return JsonResponse(
            {
                "rows": rows,
                "page": {
                    "total": paginator.count,
                    "per": per,
                    "page": page.number,
                    "has_next": page.has_next(),
                    "next_page": page.next_page_number() if page.has_next() else None,
                },
            }
        )

    qs = Capture.objects.all().order_by("-created_at")
    filtered = _apply_filters(qs, year=year, journal=journal, site=site, col=col)
    filtered = _maybe_sort(filtered, qterm="", sort=sort, direction=direction)
    paginator = Paginator(filtered, per)
    page = paginator.get_page(page_no)
    rows = [_row(c) for c in page.object_list]
    return JsonResponse(
        {
            "rows": rows,
            "page": {
                "total": paginator.count,
                "per": per,
                "page": page.number,
                "has_next": page.has_next(),
                "next_page": page.next_page_number() if page.has_next() else None,
            },
        }
    )
