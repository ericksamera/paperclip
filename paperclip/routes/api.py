from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, jsonify, request

from ..db import get_db
from ..ingest import ingest_capture


def register(app: Flask) -> None:
    @app.post("/api/captures/")
    def api_ingest_capture():
        if request.mimetype != "application/json":
            abort(415)

        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            abort(400)

        db = get_db()
        result = ingest_capture(
            payload=payload,
            db=db,
            artifacts_root=Path(app.config["ARTIFACTS_DIR"]),
            fts_enabled=bool(app.config.get("FTS_ENABLED")),
        )

        status = 201 if result.created else 200
        return (
            jsonify(
                {
                    "capture_id": result.capture_id,
                    "created": result.created,
                    "summary": result.summary,
                }
            ),
            status,
        )

    @app.get("/api/captures/<capture_id>/")
    def api_capture_get(capture_id: str):
        db = get_db()
        cap = db.execute(
            "SELECT * FROM captures WHERE id = ?", (capture_id,)
        ).fetchone()
        if not cap:
            abort(404)
        return jsonify(dict(cap))
