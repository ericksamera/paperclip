from __future__ import annotations

import re
from contextlib import suppress
from typing import Any

from captures.models import Capture, Collection
from captures.references.xref_service import enrich_capture
from paperclip.utils import norm_doi

_DOI_RE = re.compile(r"\b10\.\d{4,9}/\S+\b", re.I)


def _extract_dois(text: str) -> list[str]:
    """
    Return a sorted list of normalized DOIs found in free text.
    """
    seen: set[str] = set()
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
    """
    Returns (capture, created_flag).
    Creates a minimal Capture if needed, then attaches/enriches it.
    """
    cap = Capture.objects.filter(doi=doi).first()
    created = False
    if not cap:
        # create a minimal row; enrichment fills title/year/meta
        cap = Capture.objects.create(doi=doi, url=f"https://doi.org/{doi}")
        created = True

    _attach_to_collection(cap, collection_id)

    # Enrich immediately (synchronous minimal UX)
    with suppress(Exception):
        upd = enrich_capture(cap)
        if upd:
            for k, v in upd.items():
                setattr(cap, k, v)
            cap.save(update_fields=list(upd.keys()))

    return cap, created


def import_dois_text(raw: str, collection_id: str | None) -> dict[str, Any]:
    """
    Core logic for 'paste DOIs' imports.

    Returns a dict with:
      - ok (bool)
      - input_dois (list[str])
      - created (list[capture_id])
      - existing (list[capture_id])
      - errors (list[{doi, error}])
      - count {created, existing, errors}
    """
    dois = _extract_dois(raw)
    created: list[str] = []
    existing: list[str] = []
    errors: list[dict[str, str]] = []

    for doi in dois:
        try:
            cap, was_new = _create_or_fetch_by_doi(doi, collection_id)
            (created if was_new else existing).append(str(cap.id))
        except Exception as e:  # rare — keep importing
            errors.append({"doi": doi, "error": str(e)})

    return {
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


def import_ris_text(text: str, collection_id: str | None) -> dict[str, Any]:
    """
    Core logic for 'import .ris' — light-weight RIS handling.

    We don't try to parse RIS fully; instead we extract any DOI-looking tokens
    from the whole file and treat it like a DOI list.
    """
    dois = _extract_dois(text)
    created: list[str] = []
    existing: list[str] = []
    errors: list[dict[str, str]] = []

    for doi in dois:
        try:
            cap, was_new = _create_or_fetch_by_doi(doi, collection_id)
            (created if was_new else existing).append(str(cap.id))
        except Exception as e:
            errors.append({"doi": doi, "error": str(e)})

    return {
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
