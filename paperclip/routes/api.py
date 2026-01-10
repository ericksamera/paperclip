from __future__ import annotations

import traceback
from pathlib import Path

from flask import Flask, current_app, request

from ..apiutil import api_error, api_ok
from ..db import get_db
from ..errors import BadRequest, InternalError, NotFound
from ..fsutil import rmtree_best_effort
from ..ingest import ingest_capture
from ..ingest_schema import validate_ingest_payload
from ..services.maintenance_service import rebuild_fts, verify_fts
from ..tx import db_tx


def _artifacts_root() -> Path:
    return Path(str(current_app.config.get("ARTIFACTS_DIR") or ""))


def _maintenance_allowed() -> bool:
    return bool(current_app.config.get("DEBUG")) or bool(
        current_app.config.get("TESTING")
    )


def register(app: Flask) -> None:
    @app.post("/api/captures/")
    def api_ingest_capture():
        try:
            try:
                raw = request.get_json(force=True)
            except Exception:
                raise BadRequest(code="invalid_json", message="Invalid JSON payload")

            payload = validate_ingest_payload(raw)

            fts_enabled = bool(current_app.config.get("FTS_ENABLED"))
            with db_tx(commit=True) as db:
                res = ingest_capture(
                    payload=payload,
                    db=db,
                    artifacts_root=_artifacts_root(),
                    fts_enabled=fts_enabled,
                )

        except BadRequest:
            raise
        except Exception:
            tb = traceback.format_exc()
            details = (
                {"traceback": tb} if bool(current_app.config.get("DEBUG")) else None
            )
            raise InternalError(
                code="ingest_failed", message="Capture ingest failed", details=details
            )

        if res.cleanup_dirs:
            rmtree_best_effort(res.cleanup_dirs)

        status = 201 if res.created else 200
        return api_ok(
            {
                "capture_id": res.capture_id,
                "id": res.capture_id,
                "created": bool(res.created),
                "summary": res.summary,
            },
            status=status,
        )

    @app.get("/api/captures/<capture_id>/")
    def api_get_capture(capture_id: str):
        db = get_db()
        row = db.execute(
            "SELECT * FROM captures WHERE id = ? LIMIT 1", (capture_id,)
        ).fetchone()
        if not row:
            raise NotFound(code="not_found", message="Capture not found")
        return api_ok(dict(row), status=200)

    @app.post("/api/maintenance/rebuild-fts/")
    def api_rebuild_fts():
        if not _maintenance_allowed():
            raise NotFound(code="not_found", message="Not found")

        if not bool(current_app.config.get("FTS_ENABLED")):
            raise BadRequest(code="fts_disabled", message="FTS is disabled")

        with db_tx(commit=True) as db:
            stats = rebuild_fts(db)

        return api_ok({"ok": True, "stats": stats}, status=200)

    @app.get("/api/maintenance/verify-fts/")
    def api_verify_fts():
        if not _maintenance_allowed():
            raise NotFound(code="not_found", message="Not found")

        if not bool(current_app.config.get("FTS_ENABLED")):
            raise BadRequest(code="fts_disabled", message="FTS is disabled")

        repair_flag = (str(request.args.get("repair") or "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        repaired = False

        with db_tx(commit=True) as db:
            try:
                stats = verify_fts(db, repair=False)
                if repair_flag and not bool(stats.get("ok")):
                    stats = verify_fts(db, repair=True)
                    repaired = True
            except Exception as e:
                return api_error(
                    status=500,
                    code="fts_verify_failed",
                    message="FTS verify failed",
                    details=(
                        {"error": str(e)}
                        if bool(current_app.config.get("DEBUG"))
                        else None
                    ),
                )

        return api_ok(
            {
                "ok": bool(stats.get("ok")),
                "stats": stats,
                "repaired": bool(repaired),
            },
            status=200,
        )
