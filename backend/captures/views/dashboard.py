from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from captures.models import Collection
from captures.services.dashboard import facets_for_collection


def collection_dashboard(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    return render(request, "captures/collection_dashboard.html", {"collection": col})


def collection_summary_json(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    facets = facets_for_collection(col)
    count = col.captures.count()
    data = {
        "ok": True,
        "collection": {"id": col.id, "name": col.name, "count": count},
        **facets,
    }
    return JsonResponse(data)
