from __future__ import annotations

import uuid
from typing import Any

from flask import Response, g, has_request_context, jsonify


def _request_id() -> str:
    if has_request_context():
        rid = getattr(g, "request_id", None)
        if isinstance(rid, str) and rid.strip():
            return rid.strip()
    return uuid.uuid4().hex[:12]


def api_ok(payload: dict[str, Any], status: int = 200) -> tuple[Response, int]:
    resp = jsonify(payload)
    resp.headers["X-Request-ID"] = _request_id()
    return resp, status


def api_error(
    *,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> tuple[Response, int]:
    request_id = _request_id()
    err: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details:
        err["details"] = details

    resp = jsonify({"error": err})
    resp.headers["X-Request-ID"] = request_id
    return resp, status
