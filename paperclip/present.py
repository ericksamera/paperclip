from __future__ import annotations

from typing import Any

from .citation import citation_fields_from_meta_json


def present_capture_for_library(cap: dict[str, Any]) -> dict[str, Any]:
    """
    Adds derived citation display fields and removes meta_json.
    Intended for server-rendered templates.
    """
    citation = citation_fields_from_meta_json(cap.get("meta_json"))

    cap["authors_str"] = citation.get("authors_str") or ""
    cap["authors_short"] = citation.get("authors_short") or ""
    cap["abstract_snip"] = citation.get("abstract_snip") or ""
    cap.pop("meta_json", None)
    return cap


def present_capture_for_api(cap: dict[str, Any]) -> dict[str, Any]:
    """
    Produces the stable API shape for library rows.
    """
    citation = citation_fields_from_meta_json(cap.get("meta_json"))
    return {
        "id": cap.get("id"),
        "title": cap.get("title"),
        "url": cap.get("url"),
        "doi": cap.get("doi"),
        "year": cap.get("year"),
        "container_title": cap.get("container_title"),
        "authors_short": citation.get("authors_short") or "",
        "abstract_snip": citation.get("abstract_snip") or "",
    }
