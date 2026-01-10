from __future__ import annotations

from flask import Flask, Response, flash, request

from ..db import get_db
from ..formparams import get_capture_ids
from ..httputil import redirect_next
from ..queryparams import get_collection_arg
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
        col = get_collection_arg(request.args) or None
        capture_id = (request.args.get("capture_id") or "").strip() or None

        ctx = exports_service.select_export_context(db, capture_id=capture_id, col=col)
        body, mimetype = exports_service.render_export(
            kind="bibtex", captures=ctx.captures
        )

        filename = exports_service.export_filename(
            ext="bib",
            capture_id=ctx.capture_id,
            col_id=ctx.col_id,
            col_name=ctx.col_name,
            selected=False,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    @app.get("/exports/ris/")
    def export_ris():
        db = get_db()
        col = get_collection_arg(request.args) or None
        capture_id = (request.args.get("capture_id") or "").strip() or None

        ctx = exports_service.select_export_context(db, capture_id=capture_id, col=col)
        body, mimetype = exports_service.render_export(
            kind="ris", captures=ctx.captures
        )

        filename = exports_service.export_filename(
            ext="ris",
            capture_id=ctx.capture_id,
            col_id=ctx.col_id,
            col_name=ctx.col_name,
            selected=False,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    @app.post("/exports/bibtex/selected/")
    def export_selected_bibtex():
        capture_ids = get_capture_ids(request.form)
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        db = get_db()
        captures = exports_service.select_captures_by_ids(db, capture_ids=capture_ids)
        body, mimetype = exports_service.render_export(kind="bibtex", captures=captures)

        filename = exports_service.export_filename(
            ext="bib",
            capture_id=None,
            col_id=None,
            col_name=None,
            selected=True,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)

    @app.post("/exports/ris/selected/")
    def export_selected_ris():
        capture_ids = get_capture_ids(request.form)
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        db = get_db()
        captures = exports_service.select_captures_by_ids(db, capture_ids=capture_ids)
        body, mimetype = exports_service.render_export(kind="ris", captures=captures)

        filename = exports_service.export_filename(
            ext="ris",
            capture_id=None,
            col_id=None,
            col_name=None,
            selected=True,
        )
        return _as_download(body, mimetype=mimetype, filename=filename)
