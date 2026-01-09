from __future__ import annotations

import shutil
from pathlib import Path

from flask import Flask, request

from ..apiutil import api_error, api_ok
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
        except Exception:
            # Don’t leak internals; keep error shape stable for the extension.
            return api_error(
                status=500,
                code="internal_error",
                message="Internal server error",
            )

        # cleanup dirs only after successful commit
        for p in result.cleanup_dirs:
            try:
                shutil.rmtree(p)
            except Exception:
                pass

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
        # read-only path can stay simple; no tx wrapper needed
        from ..db import get_db

        db = get_db()
        cap = db.execute(
            "SELECT * FROM captures WHERE id = ?", (capture_id,)
        ).fetchone()
        if not cap:
            return api_error(
                status=404,
                code="not_found",
                message="Capture not found",
            )
        return api_ok(dict(cap), status=200)
