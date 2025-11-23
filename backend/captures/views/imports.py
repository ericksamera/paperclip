# backend/captures/views/imports.py
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from captures.services.imports import import_dois_text, import_ris_text


@require_http_methods(["GET"])
def imports_page(request):
    # optional prefill support could go here later
    return render(request, "captures/imports.html", {})


@require_POST
def import_dois(request):
    raw = request.POST.get("dois") or ""
    collection_id = request.POST.get("collection") or None

    data = import_dois_text(raw, collection_id)
    wants_json = "application/json" in (request.headers.get("Accept") or "")
    return JsonResponse(data) if wants_json else redirect("library")


@require_POST
def import_ris(request):
    f = request.FILES.get("ris")
    collection_id = request.POST.get("collection") or None
    if not f:
        return redirect("imports_page")

    try:
        text = f.read().decode("utf-8", errors="ignore")
    except Exception:
        text = ""

    data = import_ris_text(text, collection_id)
    wants_json = "application/json" in (request.headers.get("Accept") or "")
    return JsonResponse(data) if wants_json else redirect("library")
