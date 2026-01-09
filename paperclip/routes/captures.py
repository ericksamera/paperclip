from __future__ import annotations

import shutil
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

from ..citation import citation_fields_from_meta
from ..constants import ALLOWED_ARTIFACTS
from ..db import get_db
from ..httputil import parse_int, redirect_next
from ..metaschema import normalize_meta_record, parse_meta_json
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

        meta = normalize_meta_record(parse_meta_json(capture.get("meta_json")))
        citation = citation_fields_from_meta(meta)
        authors_str = citation.get("authors_str") or ""

        collections = captures_repo.list_collections_for_capture(db, capture_id)

        arts_root = Path(app.config["ARTIFACTS_DIR"])
        cap_dir = arts_root / capture_id
        artifact_links: dict[str, str] = {}
        for name in allowed_artifacts_list:
            if (cap_dir / name).exists():
                artifact_links[name] = url_for(
                    "artifact_download", capture_id=capture_id, name=name
                )

        return render_template(
            "capture.html",
            capture=capture,
            authors_str=authors_str,
            meta=meta,
            collections=collections,
            artifact_links=artifact_links,
        )

    @app.post("/captures/<capture_id>/collections/")
    def capture_set_collections(capture_id: str):
        selected_raw = request.form.getlist("collections") or []
        selected_ids: set[int] = set()
        for x in selected_raw:
            v = parse_int(x, -1)
            if v > 0:
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

    @app.get("/artifacts/<capture_id>/<name>/")
    def artifact_download(capture_id: str, name: str):
        if name not in allowed_artifacts_set:
            abort(404)

        arts_dir = Path(app.config["ARTIFACTS_DIR"])
        p = (arts_dir / capture_id / name).resolve()
        if not p.exists():
            abort(404)

        return send_file(p, as_attachment=True, download_name=name)

    @app.post("/captures/delete/")
    def captures_delete():
        capture_ids = request.form.getlist("capture_ids") or []
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

        for cid in capture_ids:
            try:
                shutil.rmtree(arts_dir / cid)
            except FileNotFoundError:
                pass

        flash(f"Deleted {len(capture_ids)} capture(s).", "success")
        return redirect_next("library")

    @app.post("/captures/collections/add/")
    def captures_collections_add():
        capture_ids = request.form.getlist("capture_ids") or []
        capture_ids = [c.strip() for c in capture_ids if c.strip()]
        collection_id = parse_int(request.form.get("collection_id"), -1)

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
        capture_ids = request.form.getlist("capture_ids") or []
        capture_ids = [c.strip() for c in capture_ids if c.strip()]
        collection_id = parse_int(request.form.get("collection_id"), -1)

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
