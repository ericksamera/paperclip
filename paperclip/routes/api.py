from __future__ import annotations

import traceback
from pathlib import Path

from flask import Flask, current_app, request

from ..apiutil import api_error, api_ok
from ..db import get_db
from ..fsutil import rmtree_best_effort
from ..ingest import ingest_capture
from ..services.maintenance_service import rebuild_fts, verify_fts
from ..tx import db_tx


def _artifacts_root() -> Path:
    root = current_app.config.get("ARTIFACTS_DIR")
    return Path(root)


def _maintenance_allowed() -> bool:
    return bool(current_app.config.get("DEBUG")) or bool(
        current_app.config.get("TESTING")
    )


def register(app: Flask) -> None:
    @app.post("/api/captures/")
    def api_ingest_capture():
        try:
            payload = request.get_json(force=True)
            if not isinstance(payload, dict):
                return api_error(
                    status=400,
                    code="invalid_json",
                    message="Expected a JSON object",
                )
        except Exception:
            return api_error(
                status=400,
                code="invalid_json",
                message="Invalid JSON payload",
            )

        fts_enabled = bool(current_app.config.get("FTS_ENABLED"))

        try:
            with db_tx(commit=True) as db:
                res = ingest_capture(
                    payload=payload,
                    db=db,
                    artifacts_root=_artifacts_root(),
                    fts_enabled=fts_enabled,
                )
        except Exception:
            tb = traceback.format_exc()
            return api_error(
                status=500,
                code="ingest_failed",
                message="Capture ingest failed",
                details=(
                    {"traceback": tb} if bool(current_app.config.get("DEBUG")) else None
                ),
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
            return api_error(status=404, code="not_found", message="Capture not found")
        return api_ok(dict(row), status=200)

    @app.post("/api/maintenance/rebuild-fts/")
    def api_rebuild_fts():
        if not _maintenance_allowed():
            return api_error(status=404, code="not_found", message="Not found")

        if not bool(current_app.config.get("FTS_ENABLED")):
            return api_error(
                status=400,
                code="fts_disabled",
                message="FTS is not enabled in this environment",
            )

        try:
            with db_tx(commit=True) as db:
                stats = rebuild_fts(db)
        except Exception as e:
            return api_error(
                status=500,
                code="fts_rebuild_failed",
                message="FTS rebuild failed",
                details=(
                    {"error": str(e)} if bool(current_app.config.get("DEBUG")) else None
                ),
            )

        return api_ok({"ok": True, "stats": stats}, status=200)

    @app.get("/api/maintenance/verify-fts/")
    def api_verify_fts():
        if not _maintenance_allowed():
            return api_error(status=404, code="not_found", message="Not found")

        if not bool(current_app.config.get("FTS_ENABLED")):
            return api_error(
                status=400,
                code="fts_disabled",
                message="FTS is not enabled in this environment",
            )

        repair = request.args.get("repair", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "y",
            "on",
        )

        try:
            with db_tx(commit=True) as db:
                stats = verify_fts(db)
                repaired = False

                if repair and not stats["ok"]:
                    rebuild_fts(db)
                    stats = verify_fts(db)
                    repaired = True

        except Exception as e:
            return api_error(
                status=500,
                code="fts_verify_failed",
                message="FTS verify failed",
                details=(
                    {"error": str(e)} if bool(current_app.config.get("DEBUG")) else None
                ),
            )

        return api_ok(
            {
                "ok": bool(stats["ok"]),
                "stats": stats,
                "repaired": bool(repaired),
            },
            status=200,
        )
