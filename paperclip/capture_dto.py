from __future__ import annotations

from typing import Any

from .extract import (
    best_abstract,
    best_authors,
    best_container_title,
    best_date,
    best_doi,
    best_keywords,
    best_title,
    extract_year,
    html_to_text,
    parse_head_meta,
)
from .metaschema import (
    build_meta_record,
    get_abstract,
    get_authors,
    get_keywords,
    normalize_meta_record,
    parse_meta_json,
)
from .parsers.base import ParseResult


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def merge_meta(
    client_meta: dict[str, Any], head_meta: dict[str, Any]
) -> dict[str, Any]:
    """
    Merge meta dicts into a single lowercased-key dict.
    Client meta wins when both provide the same key (because it’s “closer” to capture time),
    but practically your client meta is usually sparse.
    """
    out: dict[str, Any] = {}
    for src in (head_meta, client_meta):
        if not isinstance(src, dict):
            continue
        for k, v in src.items():
            kk = str(k).strip().lower()
            if not kk:
                continue
            out[kk] = v
    return out


def parse_summary_from_result(
    parse_result: ParseResult,
    *,
    used_for_index: bool,
    parse_exc: dict[str, Any] | None,
) -> dict[str, Any]:
    j = parse_result.to_json()
    return {
        "parser": j.get("parser", ""),
        "ok": bool(j.get("ok", False)),
        "capture_quality": j.get("capture_quality", "suspicious"),
        "blocked_reason": j.get("blocked_reason", ""),
        "confidence_fulltext": float(j.get("confidence_fulltext", 0.0)),
        "selected_hint": j.get("selected_hint", ""),
        "used_for_index": bool(used_for_index),
        "notes": j.get("notes", []),
        "error": parse_exc,
    }


def build_capture_dto_from_payload(
    *,
    payload: dict[str, Any],
    canon_url: str,
    captured_at: str,
    parse_result: ParseResult,
    parse_exc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Canonical “DTO builder” for ingestion.
    Output keys are intentionally stable so other layers stop re-deriving fields.
    """
    source_url = str(payload.get("source_url") or "").strip()

    dom_html = str(payload.get("dom_html") or "")
    extraction = _as_dict(payload.get("extraction"))
    content_html = str(extraction.get("content_html") or "")
    client_meta = _as_dict(extraction.get("meta"))

    head_meta, title_tag_text = parse_head_meta(dom_html)
    merged_meta = merge_meta(client_meta, head_meta)

    title = best_title(merged_meta, title_tag_text, source_url)
    doi = best_doi(merged_meta)
    date_str = best_date(merged_meta)
    year = extract_year(date_str)
    container_title = best_container_title(merged_meta)
    keywords = best_keywords(merged_meta)
    authors = best_authors(merged_meta)
    abstract = best_abstract(merged_meta)

    # Text for indexing/search
    base_text = html_to_text(content_html)
    parsed_text = (parse_result.article_text or "").strip()

    use_parsed_for_index = (
        bool(parsed_text)
        and parse_result.capture_quality != "blocked"
        and float(parse_result.confidence_fulltext) >= 0.45
    )

    content_text = parsed_text if use_parsed_for_index else base_text

    client = payload.get("client") if isinstance(payload.get("client"), dict) else {}

    meta_record = build_meta_record(
        head_meta=merged_meta,
        keywords=keywords,
        authors=authors,
        abstract=abstract,
        published_date_raw=date_str,
        client=client,
        extra={
            "source_url": source_url,
            "canonical_url": canon_url,
            "captured_at": captured_at,
        },
    )

    parse_summary = parse_summary_from_result(
        parse_result,
        used_for_index=use_parsed_for_index,
        parse_exc=parse_exc,
    )

    return {
        "title": title,
        "doi": doi,
        "year": year,
        "container_title": container_title,
        "authors": authors,
        "abstract": abstract,
        "keywords": keywords,
        "meta_record": meta_record,
        "content_text": content_text,
        "parse_summary": parse_summary,
        # convenience passthroughs
        "source_url": source_url,
        "canonical_url": canon_url,
        "published_date_raw": date_str,
        "client": client,
        "merged_head_meta": merged_meta,
        "dom_html": dom_html,
        "content_html": content_html,
    }


def build_capture_dto_from_row(
    row: dict[str, Any],
    *,
    content_text: str | None = None,
) -> dict[str, Any]:
    """
    Canonical “DTO builder” for data coming *out* of the DB.

    - Parses + normalizes meta_json once
    - Produces the stable keys other layers should consume
    """
    if not isinstance(row, dict):
        row = {}

    meta_record = normalize_meta_record(parse_meta_json(row.get("meta_json")))

    # Use meta_record as the authoritative normalized source for these
    authors = get_authors(meta_record)
    abstract = get_abstract(meta_record)
    keywords = get_keywords(meta_record)

    year_val = row.get("year", None)
    try:
        year_i = int(year_val) if year_val is not None else None
    except Exception:
        year_i = None

    dto: dict[str, Any] = {
        "id": row.get("id"),
        "url": row.get("url"),
        "url_canon": row.get("url_canon"),
        "url_hash": row.get("url_hash"),
        "title": str(row.get("title") or ""),
        "doi": str(row.get("doi") or ""),
        "year": year_i,
        "container_title": str(row.get("container_title") or ""),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "meta_record": meta_record,
        "authors": authors,
        "abstract": abstract,
        "keywords": keywords,
        # optional (not always selected from DB)
        "content_text": str(content_text or ""),
        # ingest-only keys not available from DB rows
        "parse_summary": {},
        "published_date_raw": str(meta_record.get("published_date_raw") or ""),
    }
    return dto
