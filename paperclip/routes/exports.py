from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, flash, request

from ..db import get_db
from ..formparams import get_capture_ids
from ..httputil import redirect_next
from ..services import exports_service


def register(app: Flask) -> None:
    def _as_download(body: str, *, mimetype: str, filename: str) -> Response:
        resp = Response(body, mimetype=mimetype)
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/exports/bibtex/")
    def export_bibtex():
        db = get_db()
        body, mimetype, filename = exports_service.export_download_parts_from_args(
            db,
            kind="bibtex",
            args=request.args,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    @app.get("/exports/ris/")
    def export_ris():
        db = get_db()
        body, mimetype, filename = exports_service.export_download_parts_from_args(
            db,
            kind="ris",
            args=request.args,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    @app.post("/exports/bibtex/selected/")
    def export_selected_bibtex():
        capture_ids = get_capture_ids(request.form)
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        db = get_db()
        body, mimetype, filename = exports_service.export_selected_download_parts(
            db,
            kind="bibtex",
            capture_ids=capture_ids,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    @app.post("/exports/ris/selected/")
    def export_selected_ris():
        capture_ids = get_capture_ids(request.form)
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        db = get_db()
        body, mimetype, filename = exports_service.export_selected_download_parts(
            db,
            kind="ris",
            capture_ids=capture_ids,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    # -------------------------
    # Master Markdown export
    # -------------------------

    @app.get("/exports/master.md/")
    def export_master_md():
        db = get_db()
        artifacts_root = Path(app.config["ARTIFACTS_DIR"])
        body, mimetype, filename = exports_service.master_md_download_parts_from_args(
            db,
            args=request.args,
            artifacts_root=artifacts_root,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    @app.post("/exports/master.md/selected/")
    def export_selected_master_md():
        capture_ids = get_capture_ids(request.form)
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        db = get_db()
        artifacts_root = Path(app.config["ARTIFACTS_DIR"])
        body, mimetype, filename = exports_service.master_md_selected_download_parts(
            db,
            capture_ids=capture_ids,
            artifacts_root=artifacts_root,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    # -------------------------
    # Sections JSON export
    # -------------------------

    @app.get("/exports/sections.json/")
    def export_sections_json():
        db = get_db()
        artifacts_root = Path(app.config["ARTIFACTS_DIR"])
        body, mimetype, filename = (
            exports_service.sections_json_download_parts_from_args(
                db,
                args=request.args,
                artifacts_root=artifacts_root,
            )
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    @app.post("/exports/sections.json/selected/")
    def export_selected_sections_json():
        capture_ids = get_capture_ids(request.form)
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        db = get_db()
        artifacts_root = Path(app.config["ARTIFACTS_DIR"])
        body, mimetype, filename = (
            exports_service.sections_json_selected_download_parts(
                db,
                capture_ids=capture_ids,
                artifacts_root=artifacts_root,
            )
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    # -------------------------
    # Papers JSONL export
    # -------------------------

    @app.get("/exports/papers.jsonl/")
    def export_papers_jsonl():
        db = get_db()
        artifacts_root = Path(app.config["ARTIFACTS_DIR"])
        body, mimetype, filename = (
            exports_service.papers_jsonl_download_parts_from_args(
                db,
                args=request.args,
                artifacts_root=artifacts_root,
            )
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    @app.post("/exports/papers.jsonl/selected/")
    def export_selected_papers_jsonl():
        capture_ids = get_capture_ids(request.form)
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        db = get_db()
        artifacts_root = Path(app.config["ARTIFACTS_DIR"])
        body, mimetype, filename = exports_service.papers_jsonl_selected_download_parts(
            db,
            capture_ids=capture_ids,
            artifacts_root=artifacts_root,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)
