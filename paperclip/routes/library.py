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
from ..present import present_capture_for_api, present_capture_for_library
from ..queryparams import library_params_from_args
from ..repo import collections_repo, library_repo


def register(app: Flask) -> None:
    @app.get("/")
    def home():
        return redirect(url_for("library"))

    @app.get("/library/")
    def library():
        db = get_db()
        p = library_params_from_args(request.args, default_page_size=50)

        collections = collections_repo.list_collections_with_counts(db)
        total_all = library_repo.count_all_captures(db)

        captures, total, has_more = library_repo.search_captures(
            db,
            q=p.q,
            selected_col=p.selected_col,
            page=p.page,
            page_size=p.page_size,
            fts_enabled=bool(current_app.config.get("FTS_ENABLED")),
        )

        out_caps = [present_capture_for_library(c) for c in captures]

        return render_template(
            "library.html",
            q=p.q,
            selected_col=p.selected_col,
            collections=collections,
            total_all=total_all,
            captures=out_caps,
            page=p.page,
            page_size=p.page_size,
            total=total,
            has_more=has_more,
            fts_enabled=bool(current_app.config.get("FTS_ENABLED")),
        )

    @app.get("/api/library/")
    def api_library():
        db = get_db()
        p = library_params_from_args(request.args, default_page_size=50)

        captures, total, has_more = library_repo.search_captures(
            db,
            q=p.q,
            selected_col=p.selected_col,
            page=p.page,
            page_size=p.page_size,
            fts_enabled=bool(current_app.config.get("FTS_ENABLED")),
        )

        # HTML rows for infinite scroll (server-rendered)
        caps_for_rows = [present_capture_for_library(c) for c in captures]
        rows_html = render_template("_library_rows.html", captures=caps_for_rows)

        # Keep JSON captures too (useful for future client-rendering)
        out_caps = [present_capture_for_api(c) for c in captures]

        return jsonify(
            {
                "captures": out_caps,
                "rows_html": rows_html,
                "page": p.page,
                "page_size": p.page_size,
                "total": total,
                "has_more": has_more,
            }
        )
