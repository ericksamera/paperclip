from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from . import artifacts
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


def present_capture_detail(
    *,
    db,
    capture_row: dict[str, Any],
    capture_id: str,
    artifacts_root: Path,
    allowed_artifacts: Iterable[str],
) -> dict[str, Any]:
    """
    Build the complete "detail page model" for a capture.

    Returns a dict with:
      - capture: stable fields for templates
      - meta: normalized meta record
      - citation: derived display fields
      - collections: list[{id,name,has_it}]
      - artifacts: list[{name,url}]
      - allowed_artifacts: list[str] (for template use)
      - parsed: { article: {...}, references: {...} } (bounded previews)
    """
    # Local import to keep most of the codebase free of Flask deps.
    from flask import url_for

    from .repo import captures_repo

    dto = build_capture_dto_from_row(capture_row)
    meta = dto["meta_record"]
    citation = citation_fields_from_meta(meta)

    capture = {
        "id": dto.get("id") or capture_id,
        "title": dto.get("title") or "",
        "url": dto.get("url") or "",
        "doi": dto.get("doi") or "",
        "year": dto.get("year"),
        "container_title": dto.get("container_title") or "",
    }

    collections = captures_repo.list_collections_for_capture(db, capture_id)

    allowed_list = list(allowed_artifacts)

    # Present artifacts (disk) filtered to allowed list
    artifact_names = artifacts.list_present_artifacts(
        artifacts_root=artifacts_root,
        capture_id=capture_id,
        allowed_artifacts=allowed_artifacts,
    )
    artifacts_list: list[dict[str, str]] = [
        {
            "name": name,
            "url": url_for("capture_artifact", capture_id=capture_id, name=name),
        }
        for name in artifact_names
    ]

    # Parsed previews (bounded, safe-ish)
    parsed = {
        "article": artifacts.read_text_artifact(
            artifacts_root=artifacts_root, capture_id=capture_id, name="article.txt"
        ),
        "references": artifacts.read_text_artifact(
            artifacts_root=artifacts_root, capture_id=capture_id, name="references.txt"
        ),
    }

    # Convenience links (so templates don't rebuild URLs)
    parsed["article"]["url"] = url_for(
        "capture_artifact", capture_id=capture_id, name="article.txt"
    )
    parsed["references"]["url"] = url_for(
        "capture_artifact", capture_id=capture_id, name="references.txt"
    )

    return {
        "capture": capture,
        "meta": meta,
        "citation": citation,
        "collections": collections,
        "artifacts": artifacts_list,
        "allowed_artifacts": allowed_list,
        "parsed": parsed,
    }
