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
from ..httputil import parse_page_size
from ..parseutil import safe_int
from ..present import present_capture_for_api, present_capture_for_library
from ..repo import collections_repo, library_repo


def _get_selected_collection() -> str:
    """
    Back-compat:
      - preferred: ?collection=<id>
      - legacy:    ?col=<id>
    """
    return (request.args.get("collection") or request.args.get("col") or "").strip()


def register(app: Flask) -> None:
    @app.get("/")
    def home():
        return redirect(url_for("library"))

    @app.get("/library/")
    def library():
        db = get_db()

        q = (request.args.get("q") or "").strip()
        selected_col = _get_selected_collection()

        page = safe_int(request.args.get("page")) or 1
        page = max(1, page)
        page_size = parse_page_size(request.args.get("page_size"), 50)

        collections = collections_repo.list_collections_with_counts(db)
        total_all = library_repo.count_all_captures(db)

        captures, total, has_more = library_repo.search_captures(
            db,
            q=q,
            selected_col=selected_col,
            page=page,
            page_size=page_size,
            fts_enabled=bool(current_app.config.get("FTS_ENABLED")),
        )

        out_caps = [present_capture_for_library(c) for c in captures]

        return render_template(
            "library.html",
            q=q,
            selected_col=selected_col,
            collections=collections,
            total_all=total_all,
            captures=out_caps,
            page=page,
            page_size=page_size,
            total=total,
            has_more=has_more,
            fts_enabled=bool(current_app.config.get("FTS_ENABLED")),
        )

    @app.get("/api/library/")
    def api_library():
        db = get_db()

        q = (request.args.get("q") or "").strip()
        selected_col = _get_selected_collection()

        page = safe_int(request.args.get("page")) or 1
        page = max(1, page)
        page_size = parse_page_size(request.args.get("page_size"), 50)

        captures, total, has_more = library_repo.search_captures(
            db,
            q=q,
            selected_col=selected_col,
            page=page,
            page_size=page_size,
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
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_more": has_more,
            }
        )
