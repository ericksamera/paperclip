from __future__ import annotations

import uuid
from typing import Any

from flask import Response, jsonify


def api_ok(payload: dict[str, Any], status: int = 200) -> tuple[Response, int]:
    return jsonify(payload), status


def api_error(
    *,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> tuple[Response, int]:
    request_id = uuid.uuid4().hex[:12]
    err: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details:
        err["details"] = details

    resp = jsonify({"error": err})
    resp.headers["X-Request-ID"] = request_id
    return resp, status
