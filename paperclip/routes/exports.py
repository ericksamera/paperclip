from __future__ import annotations

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
