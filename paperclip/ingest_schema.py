from __future__ import annotations

from typing import Any

from .errors import BadRequest


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def validate_ingest_payload(payload: Any) -> dict[str, Any]:
    """
    API-layer validation/coercion for /api/captures/ payloads.

    - Requires top-level JSON object (dict)
    - Requires non-empty source_url
    - Coerces dom_html to a string
    - Coerces extraction/meta to dicts (so parser + DTO stay best-effort)
    """
    if not isinstance(payload, dict):
        raise BadRequest(code="invalid_json", message="Expected a JSON object")

    source_url = str(payload.get("source_url") or "").strip()
    if not source_url:
        raise BadRequest(
            code="missing_field",
            message="Missing required field: source_url",
            details={"field": "source_url"},
        )

    # Coerce common fields (best-effort ingest)
    out: dict[str, Any] = dict(payload)
    out["source_url"] = source_url
    out["dom_html"] = str(payload.get("dom_html") or "")

    extraction = _as_dict(payload.get("extraction"))
    meta = _as_dict(extraction.get("meta"))
    extraction["meta"] = meta
    out["extraction"] = extraction

    return out
