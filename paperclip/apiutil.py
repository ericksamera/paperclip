from __future__ import annotations

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
    err: dict[str, Any] = {"code": code, "message": message}
    if details:
        err["details"] = details
    return jsonify({"error": err}), status
