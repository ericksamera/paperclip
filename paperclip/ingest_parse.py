from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any

from .capture_dto import build_capture_dto_from_payload
from .parsers import parse_article
from .parsers.base import ParseResult
from .timeutil import utc_now_iso
from .urlnorm import canonicalize_url, url_hash
from .util import as_dict


@dataclass(frozen=True)
class ParsedPayload:
    raw_payload: dict[str, Any]
    source_url: str
    canon_url: str
    url_hash: str
    captured_at: str
    dom_html: str
    client_meta: dict[str, Any]
    parse_result: ParseResult
    parse_exc: dict[str, Any] | None
    dto: dict[str, Any]


def parse_payload(payload: dict[str, Any]) -> ParsedPayload:
    """
    Validate + canonicalize + parse + build DTO.
    Keeps ingestion "best-effort": parser failure should not block saving.
    """
    now = utc_now_iso()

    source_url = str(payload.get("source_url") or "").strip()
    if not source_url:
        raise ValueError("Missing required field: source_url")

    canon = canonicalize_url(source_url)
    h = url_hash(canon)

    dom_html = str(payload.get("dom_html") or "")
    extraction = as_dict(payload.get("extraction"))
    client_meta = as_dict(extraction.get("meta"))

    parse_exc: dict[str, Any] | None = None
    try:
        parse_result = parse_article(
            url=canon, dom_html=dom_html, head_meta=client_meta
        )
    except Exception as e:
        parse_exc = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
        }
        parse_result = ParseResult(
            ok=False,
            parser="crashed",
            capture_quality="suspicious",
            notes=["parser_exception"],
        )

    dto = build_capture_dto_from_payload(
        payload=payload,
        canon_url=canon,
        captured_at=now,
        parse_result=parse_result,
        parse_exc=parse_exc,
    )

    return ParsedPayload(
        raw_payload=payload,
        source_url=source_url,
        canon_url=canon,
        url_hash=h,
        captured_at=now,
        dom_html=dom_html,
        client_meta=client_meta,
        parse_result=parse_result,
        parse_exc=parse_exc,
        dto=dto,
    )
