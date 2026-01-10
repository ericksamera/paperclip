from __future__ import annotations

import traceback
from pathlib import Path

from flask import Flask, current_app, request

from ..apiutil import api_error, api_ok
from ..fsutil import rmtree_best_effort
from ..ingest import ingest_capture
from ..tx import db_tx


def register(app: Flask) -> None:
    @app.post("/api/captures/")
    def api_ingest_capture():
        if request.mimetype != "application/json":
            return api_error(
                status=415,
                code="unsupported_media_type",
                message="Content-Type must be application/json",
            )

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return api_error(
                status=400,
                code="bad_request",
                message="Request body must be a JSON object",
            )

        arts_root = Path(app.config["ARTIFACTS_DIR"])
        fts_enabled = bool(app.config.get("FTS_ENABLED"))

        try:
            with db_tx() as db:
                result = ingest_capture(
                    payload=payload,
                    db=db,
                    artifacts_root=arts_root,
                    fts_enabled=fts_enabled,
                )
        except ValueError as e:
            return api_error(status=400, code="bad_request", message=str(e))
        except Exception as e:
            # In dev/tests, surface details so we can fix the real root cause.
            current_app.logger.exception("POST /api/captures/ failed")
            if current_app.testing or bool(current_app.config.get("DEBUG")):
                return api_error(
                    status=500,
                    code="internal_error",
                    message=str(e) or "Internal server error",
                    details={"traceback": traceback.format_exc()},
                )
            return api_error(
                status=500,
                code="internal_error",
                message="Internal server error",
            )

        # cleanup dirs only after successful commit
        rmtree_best_effort(result.cleanup_dirs)

        status = 201 if result.created else 200
        return api_ok(
            {
                "capture_id": result.capture_id,
                "created": result.created,
                "summary": result.summary,
            },
            status=status,
        )

    @app.get("/api/captures/<capture_id>/")
    def api_capture_get(capture_id: str):
        from ..db import get_db

        db = get_db()
        cap = db.execute(
            "SELECT * FROM captures WHERE id = ?",
            (capture_id,),
        ).fetchone()
        if not cap:
            return api_error(status=404, code="not_found", message="Capture not found")
        return api_ok(dict(cap), status=200)
