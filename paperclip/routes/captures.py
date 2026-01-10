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

from ..constants import ALLOWED_ARTIFACTS
from ..db import get_db
from ..formparams import get_capture_ids, get_collection_id, get_collection_ids
from ..fsutil import rmtree_best_effort
from ..httputil import redirect_next
from ..present import present_capture_detail
from ..repo import captures_repo
from ..timeutil import utc_now_iso
from ..tx import db_tx


def register(app: Flask) -> None:
    allowed_artifacts_set = set(ALLOWED_ARTIFACTS)

    @app.get("/captures/<capture_id>/")
    def capture_detail(capture_id: str):
        db = get_db()
        row = captures_repo.get_capture(db, capture_id)
        if not row:
            abort(404)

        model = present_capture_detail(
            db=db,
            capture_row=row,
            capture_id=capture_id,
            artifacts_root=Path(app.config["ARTIFACTS_DIR"]),
            allowed_artifacts=ALLOWED_ARTIFACTS,
        )

        return render_template(
            "capture.html",
            capture=model["capture"],
            meta=model["meta"],
            citation=model["citation"],
            collections=model["collections"],
            artifacts=model["artifacts"],
            allowed_artifacts=model["allowed_artifacts"],
            parsed=model["parsed"],  # <-- FIX
        )

    @app.get("/captures/<capture_id>/artifact/<name>")
    def capture_artifact(capture_id: str, name: str):
        if name not in allowed_artifacts_set:
            abort(404)
        p = Path(app.config["ARTIFACTS_DIR"]) / capture_id / name
        if not p.exists():
            abort(404)
        return send_file(p)

    @app.post("/captures/<capture_id>/collections/set/")
    def capture_set_collections(capture_id: str):
        selected_ids = get_collection_ids(request.form, field="collection_ids")

        now = utc_now_iso()
        with db_tx() as db:
            cap = db.execute(
                "SELECT id FROM captures WHERE id = ?", (capture_id,)
            ).fetchone()
            if not cap:
                abort(404)

            captures_repo.set_capture_collections(
                db,
                capture_id=capture_id,
                selected_ids=selected_ids,
                now=now,
            )

        flash("Collections updated.", "success")
        return redirect(url_for("capture_detail", capture_id=capture_id))

    @app.post("/captures/delete/")
    def captures_delete():
        capture_ids = get_capture_ids(request.form)
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        arts_dir = Path(app.config["ARTIFACTS_DIR"])
        fts_enabled = bool(app.config.get("FTS_ENABLED"))

        with db_tx() as db:
            captures_repo.delete_captures(
                db, capture_ids=capture_ids, fts_enabled=fts_enabled
            )

        rmtree_best_effort([arts_dir / cid for cid in capture_ids])

        flash(f"Deleted {len(capture_ids)} capture(s).", "success")
        return redirect_next("library")

    @app.post("/captures/collections/add/")
    def captures_collections_add():
        capture_ids = get_capture_ids(request.form)
        collection_id = get_collection_id(request.form)

        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        if not collection_id:
            flash("Pick a collection.", "warning")
            return redirect_next("library")

        now = utc_now_iso()
        with db_tx() as db:
            captures_repo.bulk_add_to_collection(
                db,
                capture_ids=capture_ids,
                collection_id=collection_id,
                now=now,
            )

        flash(f"Added {len(capture_ids)} capture(s) to collection.", "success")
        return redirect_next("library")

    @app.post("/captures/collections/remove/")
    def captures_collections_remove():
        capture_ids = get_capture_ids(request.form)
        collection_id = get_collection_id(request.form)

        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        if not collection_id:
            flash("Pick a collection.", "warning")
            return redirect_next("library")

        now = utc_now_iso()
        with db_tx() as db:
            captures_repo.bulk_remove_from_collection(
                db,
                capture_ids=capture_ids,
                collection_id=collection_id,
                now=now,
            )

        flash(f"Removed {len(capture_ids)} capture(s) from collection.", "success")
        return redirect_next("library")
