from __future__ import annotations

from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from .. import artifacts
from ..constants import ALLOWED_ARTIFACTS
from ..db import get_db
from ..formparams import get_capture_ids, get_collection_id, get_collection_ids
from ..httputil import redirect_next
from ..services import captures_service
from ..timeutil import utc_now_iso
from ..tx import db_tx
from ..util import rmtree_best_effort


def register(app: Flask) -> None:
    @app.get("/captures/<capture_id>/")
    def capture_detail(capture_id: str):
        db = get_db()

        ctx = captures_service.capture_detail_context(
            db,
            capture_id=capture_id,
            artifacts_root=Path(app.config["ARTIFACTS_DIR"]),
            allowed_artifacts=ALLOWED_ARTIFACTS,
        )
        if not ctx:
            abort(404)

        return render_template("capture.html", **ctx)

    @app.get("/captures/<capture_id>/artifact/<name>")
    def capture_artifact(capture_id: str, name: str):
        if name not in artifacts.ALLOWED_ARTIFACTS_SET:
            abort(404)

        p = artifacts.artifact_path(Path(app.config["ARTIFACTS_DIR"]), capture_id, name)
        if not p.exists():
            abort(404)
        return send_file(p)

    @app.post("/captures/<capture_id>/collections/set/")
    def capture_set_collections(capture_id: str):
        selected_ids = get_collection_ids(request.form, field="collection_ids")
        now = utc_now_iso()

        with db_tx() as db:
            res = captures_service.set_capture_collections(
                db,
                capture_id=capture_id,
                selected_ids=selected_ids,
                now=now,
            )

        flash(res.message, res.category)
        if not res.ok:
            abort(404)
        return redirect(url_for("capture_detail", capture_id=capture_id))

    @app.post("/captures/delete/")
    def captures_delete():
        capture_ids = get_capture_ids(request.form)
        arts_dir = Path(app.config["ARTIFACTS_DIR"])
        fts_enabled = bool(app.config.get("FTS_ENABLED"))

        with db_tx() as db:
            res = captures_service.delete_captures(
                db,
                capture_ids=capture_ids,
                artifacts_root=arts_dir,
                fts_enabled=fts_enabled,
            )

        if res.cleanup_paths:
            rmtree_best_effort(res.cleanup_paths)

        flash(res.message, res.category)
        return redirect_next("library")

    @app.post("/captures/collections/add/")
    def captures_collections_add():
        capture_ids = get_capture_ids(request.form)
        collection_id = get_collection_id(request.form)
        now = utc_now_iso()

        with db_tx() as db:
            res = captures_service.bulk_add_to_collection(
                db,
                capture_ids=capture_ids,
                collection_id=collection_id,
                now=now,
            )

        flash(res.message, res.category)
        return redirect_next("library")

    @app.post("/captures/collections/remove/")
    def captures_collections_remove():
        capture_ids = get_capture_ids(request.form)
        collection_id = get_collection_id(request.form)
        now = utc_now_iso()

        with db_tx() as db:
            res = captures_service.bulk_remove_from_collection(
                db,
                capture_ids=capture_ids,
                collection_id=collection_id,
                now=now,
            )

        flash(res.message, res.category)
        return redirect_next("library")
