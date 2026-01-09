from __future__ import annotations

import re

from flask import Flask, Response, flash, request

from ..db import get_db
from ..export import captures_to_bibtex, captures_to_ris
from ..httputil import redirect_next
from ..repo import exports_repo


def register(app: Flask) -> None:
    def _slug(s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"[^a-z0-9]+", "-", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
        return s[:80] if s else "export"

    def _export_filename(
        *,
        ext: str,
        capture_id: str | None,
        col_id: int | None,
        col_name: str | None,
        selected: bool,
    ) -> str:
        base = "paperclip"

        if capture_id:
            base = f"{base}_{_slug(capture_id)[:12]}"
        elif col_name:
            base = f"{base}_{_slug(col_name)}"
        elif col_id:
            base = f"{base}_col{col_id}"

        if selected:
            base = f"{base}_selected"

        return f"{base}.{ext}"

    def _as_download(body: str, *, mimetype: str, filename: str) -> Response:
        resp = Response(body, mimetype=mimetype)
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def _get_collection_arg() -> str | None:
        # Preferred: ?collection=<id>
        # Back-compat: ?col=<id>
        v = (request.args.get("collection") or request.args.get("col") or "").strip()
        return v or None

    @app.get("/exports/bibtex/")
    def export_bibtex():
        db = get_db()
        captures, capture_id, col_id, col_name = (
            exports_repo.select_captures_for_export(
                db,
                capture_id=(request.args.get("capture_id") or "").strip() or None,
                col=_get_collection_arg(),
            )
        )
        bib = captures_to_bibtex(captures)
        filename = _export_filename(
            ext="bib",
            capture_id=capture_id,
            col_id=col_id,
            col_name=col_name,
            selected=False,
        )
        return _as_download(bib, mimetype="application/x-bibtex", filename=filename)

    @app.get("/exports/ris/")
    def export_ris():
        db = get_db()
        captures, capture_id, col_id, col_name = (
            exports_repo.select_captures_for_export(
                db,
                capture_id=(request.args.get("capture_id") or "").strip() or None,
                col=_get_collection_arg(),
            )
        )
        ris = captures_to_ris(captures)
        filename = _export_filename(
            ext="ris",
            capture_id=capture_id,
            col_id=col_id,
            col_name=col_name,
            selected=False,
        )
        return _as_download(
            ris,
            mimetype="application/x-research-info-systems",
            filename=filename,
        )

    @app.post("/exports/bibtex/selected/")
    def export_selected_bibtex():
        capture_ids = request.form.getlist("capture_ids") or []
        capture_ids = [c.strip() for c in capture_ids if c.strip()]
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        db = get_db()
        captures = exports_repo.select_captures_by_ids(db, capture_ids=capture_ids)
        bib = captures_to_bibtex(captures)
        filename = _export_filename(
            ext="bib",
            capture_id=None,
            col_id=None,
            col_name=None,
            selected=True,
        )
        return _as_download(bib, mimetype="application/x-bibtex", filename=filename)

    @app.post("/exports/ris/selected/")
    def export_selected_ris():
        capture_ids = request.form.getlist("capture_ids") or []
        capture_ids = [c.strip() for c in capture_ids if c.strip()]
        if not capture_ids:
            flash("No captures selected.", "warning")
            return redirect_next("library")

        db = get_db()
        captures = exports_repo.select_captures_by_ids(db, capture_ids=capture_ids)
        ris = captures_to_ris(captures)
        filename = _export_filename(
            ext="ris",
            capture_id=None,
            col_id=None,
            col_name=None,
            selected=True,
        )
        return _as_download(
            ris,
            mimetype="application/x-research-info-systems",
            filename=filename,
        )
