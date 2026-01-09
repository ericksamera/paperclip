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

from ..capture_dto import build_capture_dto_from_row
from ..citation import citation_fields_from_meta
from ..constants import ALLOWED_ARTIFACTS
from ..db import get_db
from ..fsutil import rmtree_best_effort
from ..httputil import redirect_next
from ..parseutil import safe_int
from ..repo import captures_repo
from ..timeutil import utc_now_iso
from ..tx import db_tx


def register(app: Flask) -> None:
    allowed_artifacts_set = set(ALLOWED_ARTIFACTS)
    allowed_artifacts_list = list(ALLOWED_ARTIFACTS)

    @app.get("/captures/<capture_id>/")
    def capture_detail(capture_id: str):
        db = get_db()
        capture = captures_repo.get_capture(db, capture_id)
        if not capture:
            abort(404)

        dto = build_capture_dto_from_row(capture)
        meta = dto["meta_record"]
        citation = citation_fields_from_meta(meta)

        # Collections list with has_it flags for this capture
        collections = captures_repo.list_collections_for_capture(db, capture_id)

        artifacts_dir = Path(app.config["ARTIFACTS_DIR"]) / capture_id
        artifacts: list[dict] = []
        if artifacts_dir.exists():
            for p in artifacts_dir.iterdir():
                if p.is_file() and p.name in allowed_artifacts_set:
                    artifacts.append(
                        {
                            "name": p.name,
                            "url": url_for(
                                "capture_artifact", capture_id=capture_id, name=p.name
                            ),
                        }
                    )

        return render_template(
            "capture.html",
            capture=capture,
            meta=meta,
            citation=citation,
            collections=collections,
            artifacts=artifacts,
            allowed_artifacts=allowed_artifacts_list,
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
        # NOTE: template uses name="collection_ids"
        selected_raw = request.form.getlist("collection_ids")
        selected_ids: set[int] = set()
        for x in selected_raw:
            v = safe_int(x)
            if v and v > 0:
                selected_ids.add(v)

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
        capture_ids = request.form.getlist("capture_ids")
        capture_ids = [c.strip() for c in capture_ids if c.strip()]
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        arts_dir = Path(app.config["ARTIFACTS_DIR"])
        fts_enabled = bool(app.config.get("FTS_ENABLED"))

        with db_tx() as db:
            captures_repo.delete_captures(
                db, capture_ids=capture_ids, fts_enabled=fts_enabled
            )

        # delete artifacts after commit
        rmtree_best_effort([arts_dir / cid for cid in capture_ids])

        flash(f"Deleted {len(capture_ids)} capture(s).", "success")
        return redirect_next("library")

    @app.post("/captures/collections/add/")
    def captures_collections_add():
        capture_ids = request.form.getlist("capture_ids")
        capture_ids = [c.strip() for c in capture_ids if c.strip()]
        collection_id = safe_int(request.form.get("collection_id")) or -1

        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        if collection_id <= 0:
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
        capture_ids = request.form.getlist("capture_ids")
        capture_ids = [c.strip() for c in capture_ids if c.strip()]
        collection_id = safe_int(request.form.get("collection_id")) or -1

        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        if collection_id <= 0:
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
