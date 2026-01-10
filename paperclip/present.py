from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

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


def _read_text_artifact(
    *, cap_dir: Path, name: str, max_chars: int = 120_000
) -> dict[str, Any]:
    """
    Safe-ish helper for capture detail page.
    Reads a UTF-8-ish text artifact with a hard max size, and reports truncation.
    Never raises.
    """
    p = cap_dir / name
    if not p.exists() or not p.is_file():
        return {
            "name": name,
            "exists": False,
            "text": "",
            "truncated": False,
            "chars": 0,
        }

    try:
        raw = p.read_bytes()
    except Exception:
        return {
            "name": name,
            "exists": True,
            "text": "",
            "truncated": False,
            "chars": 0,
        }

    # Decode best-effort
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = ""

    chars = len(text)
    if chars > max_chars:
        text = text[:max_chars].rstrip() + "\n… (truncated)"
        return {
            "name": name,
            "exists": True,
            "text": text,
            "truncated": True,
            "chars": chars,
        }

    return {
        "name": name,
        "exists": True,
        "text": text,
        "truncated": False,
        "chars": chars,
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

    allowed_set = set(allowed_artifacts)
    allowed_list = list(allowed_artifacts)

    cap_dir = artifacts_root / capture_id

    artifacts: list[dict[str, str]] = []
    if cap_dir.exists():
        for p in cap_dir.iterdir():
            if p.is_file() and p.name in allowed_set:
                artifacts.append(
                    {
                        "name": p.name,
                        "url": url_for(
                            "capture_artifact", capture_id=capture_id, name=p.name
                        ),
                    }
                )

    # Parsed previews (future-friendly: can add sections/figures/etc later)
    parsed = {
        "article": _read_text_artifact(cap_dir=cap_dir, name="article.txt"),
        "references": _read_text_artifact(cap_dir=cap_dir, name="references.txt"),
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
        "artifacts": artifacts,
        "allowed_artifacts": allowed_list,
        "parsed": parsed,
    }
