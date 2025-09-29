from __future__ import annotations
from typing import Any, Dict, List

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from captures.models import Capture
from captures.search import search_ids

from .common import _row, _apply_filters, _build_facets, _collections_with_counts


class LibraryView(View):
    template_name = "captures/list.html"

    def get(self, request):
        sort = (request.GET.get("sort") or "created_at").strip()
        direction = (request.GET.get("dir") or "desc").strip().lower()
        page_no = int(request.GET.get("page") or 1)
        per = int(request.GET.get("per") or 200)
        qterm = (request.GET.get("q") or "").strip()
        year = (request.GET.get("year") or "").strip()
        journal = (request.GET.get("journal") or "").strip().lower()
        site = (request.GET.get("site") or "").strip().lower()
        col = (request.GET.get("col") or "").strip()

        sort_map = {"title": "title", "year": "year", "created_at": "created_at", "journal": "created_at"}
        key = sort_map.get(sort, "created_at")
        order_by = f"-{key}" if direction == "desc" else key

        base_qs = Capture.objects.all().order_by(order_by)
        facets = _build_facets(base_qs)
        collections = _collections_with_counts()

        if qterm:
            ids = search_ids(qterm)
            rank = {pk: i for i, pk in enumerate(ids)}
            fts_qs = Capture.objects.filter(id__in=ids)
            filtered = _apply_filters(fts_qs, year=year, journal=journal, site=site, col=col)
            filtered.sort(key=lambda c: rank.get(str(c.id), 10**9))
            total = len(filtered)
            start, end = (page_no - 1) * per, (page_no - 1) * per + per
            rows = [_row(c) for c in filtered[start:end]]
            return render(request, self.template_name, {
                "rows": rows, "count": total, "sort": sort, "dir": direction,
                "current_params": request.GET,
                "selected": {"q": qterm, "year": year, "journal": journal, "site": site, "col": col},
                "facets": facets, "collections": collections,
            })

        filtered = _apply_filters(base_qs, year=year, journal=journal, site=site, col=col)
        paginator = Paginator(filtered, per)
        page = paginator.get_page(page_no)
        rows = [_row(c) for c in page.object_list]
        return render(request, self.template_name, {
            "rows": rows, "count": paginator.count, "sort": sort, "dir": direction,
            "current_params": request.GET,
            "selected": {"q": qterm, "year": year, "journal": journal, "site": site, "col": col},
            "facets": facets, "collections": collections,
        })


def library_page(request):
    per = int(request.GET.get("per") or 200)
    page_no = int(request.GET.get("page") or 1)
    qs = Capture.objects.all().order_by("-created_at")
    year = (request.GET.get("year") or "").strip()
    journal = (request.GET.get("journal") or "").strip().lower()
    site = (request.GET.get("site") or "").strip().lower()
    col = (request.GET.get("col") or "").strip()
    filtered = _apply_filters(qs, year=year, journal=journal, site=site, col=col)
    paginator = Paginator(filtered, per)
    page = paginator.get_page(page_no)
    rows = [_row(c) for c in page.object_list]
    return JsonResponse({
        "rows": rows,
        "page": {
            "total": paginator.count,
            "per": per,
            "page": page.number,
            "has_next": page.has_next(),
            "next_page": page.next_page_number() if page.has_next() else None,
        }
    })
