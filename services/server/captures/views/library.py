from __future__ import annotations
from typing import List, Dict, Tuple

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from captures.models import Capture
from captures.search import search_ids
from .common import _row, _apply_filters, _build_facets, _collections_with_counts


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


# ------------------------ views ------------------------

class LibraryView(View):
    template_name = "captures/list.html"

    def get(self, request):
        sort = request.GET.get("sort", "created_at")
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

        if qterm:
            ids = _search_ids_for_query(qterm, search_mode)
            filtered, _rank = _filter_and_rank(ids, year=year, journal=journal, site=site, col=col)
            total = len(filtered)
            start = (page_no - 1) * per
            end = start + per
            rows = [_row(c) for c in filtered[start:end]]

            # “All items” count for the Collections header when a search is active
            all_items_filtered = _apply_filters(Capture.objects.filter(id__in=ids), year=year, journal=journal, site=site, col="")
            collections_all_count = len(all_items_filtered)

            return render(
                request,
                self.template_name,
                {
                    "rows": rows,
                    "count": total,
                    "sort": sort,
                    "dir": direction,
                    "current_params": request.GET,
                    "selected": {"q": qterm, "year": year, "journal": journal, "site": site, "col": col},
                    "facets": facets,
                    "collections": collections,
                    "collections_all_count": collections_all_count,
                },
            )

        # Non-search listing (simple ordering + pagination)
        filtered = _apply_filters(base_qs, year=year, journal=journal, site=site, col=col)
        paginator = Paginator(filtered, per)
        page = paginator.get_page(page_no)
        rows = [_row(c) for c in page.object_list]
        all_items_filtered = _apply_filters(base_qs, year=year, journal=journal, site=site, col="")
        collections_all_count = len(all_items_filtered)

        return render(
            request,
            self.template_name,
            {
                "rows": rows,
                "count": paginator.count,
                "sort": sort,
                "dir": direction,
                "current_params": request.GET,
                "selected": {"q": qterm, "year": year, "journal": journal, "site": site, "col": col},
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

    if qterm:
        ids = _search_ids_for_query(qterm, search_mode)
        filtered, _rank = _filter_and_rank(ids, year=year, journal=journal, site=site, col=col)
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
