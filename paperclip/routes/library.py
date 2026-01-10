from __future__ import annotations

from flask import (
    Flask,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from ..db import get_db
from ..services.library_service import (
    api_library_response_from_args,
    library_page_context_from_args,
)


def register(app: Flask) -> None:
    @app.get("/")
    def home():
        return redirect(url_for("library"))

    @app.get("/library/")
    def library():
        db = get_db()
        fts_enabled = bool(current_app.config.get("FTS_ENABLED"))

        ctx = library_page_context_from_args(
            db,
            args=request.args,
            fts_enabled=fts_enabled,
            default_page_size=50,
        )
        return render_template("library.html", **ctx)

    @app.get("/api/library/")
    def api_library():
        db = get_db()
        fts_enabled = bool(current_app.config.get("FTS_ENABLED"))

        def _render_rows(captures):
            return render_template("_library_rows.html", captures=captures)

        payload = api_library_response_from_args(
            db,
            args=request.args,
            fts_enabled=fts_enabled,
            render_rows=_render_rows,
            default_page_size=50,
        )
        return jsonify(payload)
