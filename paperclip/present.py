from __future__ import annotations

from typing import Any

from .capture_dto import build_capture_dto_from_row
from .citation import citation_fields_from_meta


def present_capture_for_library(cap: dict[str, Any]) -> dict[str, Any]:
    """
    Adds derived citation display fields for templates.

    IMPORTANT:
    This function must NOT mutate the input dict, because the same row dict may be
    reused (e.g., API route builds rows_html and JSON captures from the same list).
    """
    cap2 = dict(cap)

    dto = build_capture_dto_from_row(cap2)
    meta = dto["meta_record"]
    citation = citation_fields_from_meta(meta)

    cap2["authors_str"] = citation.get("authors_str") or ""
    cap2["authors_short"] = citation.get("authors_short") or ""
    cap2["abstract_snip"] = citation.get("abstract_snip") or ""

    # Keep templates from accidentally depending on meta_json again
    cap2.pop("meta_json", None)
    return cap2


def present_capture_for_api(cap: dict[str, Any]) -> dict[str, Any]:
    """
    Produces the stable API shape for library rows.
    """
    dto = build_capture_dto_from_row(cap)
    citation = citation_fields_from_meta(dto["meta_record"])

    return {
        "id": dto.get("id"),
        "title": dto.get("title"),
        "url": dto.get("url"),
        "doi": dto.get("doi"),
        "year": dto.get("year"),
        "container_title": dto.get("container_title"),
        "authors_short": citation.get("authors_short") or "",
        "abstract_snip": citation.get("abstract_snip") or "",
    }
