# services/server/captures/views/imports.py
from __future__ import annotations

import re
from contextlib import suppress

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from captures.models import Capture, Collection
from captures.xref import enrich_capture_via_crossref
from paperclip.utils import norm_doi

_DOI_RE = re.compile(r"\b10\.\d{4,9}/\S+\b", re.I)


def _extract_dois(text: str) -> list[str]:
    seen = set()
    for m in _DOI_RE.finditer(text or ""):
        doi = norm_doi(m.group(0))
        if doi:
            seen.add(doi)
    return sorted(seen)


def _attach_to_collection(cap: Capture, collection_id: str | None) -> None:
    if not collection_id:
        return
    col = Collection.objects.filter(pk=collection_id).first()
    if col:
        col.captures.add(cap)


def _create_or_fetch_by_doi(
    doi: str, collection_id: str | None
) -> tuple[Capture, bool]:
    """Returns (capture, created_flag)."""
    cap = Capture.objects.filter(doi=doi).first()
    created = False
    if not cap:
        # create a minimal row; enrichment fills title/year/meta
        cap = Capture.objects.create(doi=doi, url=f"https://doi.org/{doi}")
        created = True
    _attach_to_collection(cap, collection_id)
    # Enrich immediately (synchronous minimal UX)
    with suppress(Exception):
        upd = enrich_capture_via_crossref(cap)
        if upd:
            for k, v in upd.items():
                setattr(cap, k, v)
            cap.save(update_fields=list(upd.keys()))
    return cap, created


@require_http_methods(["GET"])
def imports_page(request):
    # optional prefill
    return render(request, "captures/imports.html", {})


@require_POST
def import_dois(request):
    raw = request.POST.get("dois") or ""
    collection_id = request.POST.get("collection") or None
    dois = _extract_dois(raw)
    created, existing, errors = [], [], []

    for doi in dois:
        try:
            cap, was_new = _create_or_fetch_by_doi(doi, collection_id)
            (created if was_new else existing).append(str(cap.id))
        except Exception as e:  # rare — keep importing
            errors.append({"doi": doi, "error": str(e)})

    data = {
        "ok": True,
        "input_dois": dois,
        "created": created,
        "existing": existing,
        "errors": errors,
        "count": {
            "created": len(created),
            "existing": len(existing),
            "errors": len(errors),
        },
    }
    # JSON if fetch; otherwise bounce to Library
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
    # Light-weight RIS approach: extract DOIs anywhere in the file
    dois = _extract_dois(text)
    created, existing, errors = [], [], []

    for doi in dois:
        try:
            cap, was_new = _create_or_fetch_by_doi(doi, collection_id)
            (created if was_new else existing).append(str(cap.id))
        except Exception as e:
            errors.append({"doi": doi, "error": str(e)})

    data = {
        "ok": True,
        "input_dois": dois,
        "created": created,
        "existing": existing,
        "errors": errors,
        "count": {
            "created": len(created),
            "existing": len(existing),
            "errors": len(errors),
        },
    }
    wants_json = "application/json" in (request.headers.get("Accept") or "")
    return JsonResponse(data) if wants_json else redirect("library")
