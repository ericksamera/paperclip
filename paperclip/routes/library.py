from __future__ import annotations

from typing import Any

from flask import (
    Flask,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from ..citation import citation_fields_from_meta_json
from ..db import get_db
from ..httputil import parse_int, parse_page_size
from ..repo import library_repo


def register(app: Flask) -> None:
    @app.get("/")
    def home():
        return redirect(url_for("library"))

    @app.get("/library/")
    def library():
        db = get_db()
        q = (request.args.get("q") or "").strip()
        selected_col = (request.args.get("col") or "").strip()
        page = max(1, parse_int(request.args.get("page"), 1))
        page_size = parse_page_size(request.args.get("page_size"), 50)

        collections = library_repo.list_collections_with_counts(db)
        total_all = library_repo.count_all_captures(db)

        captures, total, has_more = library_repo.search_captures(
            db,
            q=q,
            selected_col=selected_col,
            page=page,
            page_size=page_size,
            fts_enabled=bool(current_app.config.get("FTS_ENABLED")),
        )

        for cap in captures:
            citation = citation_fields_from_meta_json(cap.get("meta_json"))
            cap["authors_str"] = citation.get("authors_str") or ""
            cap["authors_short"] = citation.get("authors_short") or ""
            cap["abstract_snip"] = citation.get("abstract_snip") or ""
            cap.pop("meta_json", None)

        return render_template(
            "library.html",
            q=q,
            selected_col=selected_col,
            page=page,
            page_size=page_size,
            total=total,
            total_all=total_all,
            has_more=has_more,
            captures=captures,
            collections=collections,
        )

    @app.get("/api/library/")
    def api_library():
        db = get_db()
        q = (request.args.get("q") or "").strip()
        selected_col = (request.args.get("col") or "").strip()
        page = max(1, parse_int(request.args.get("page"), 1))
        page_size = parse_page_size(request.args.get("page_size"), 50)

        captures, total, has_more = library_repo.search_captures(
            db,
            q=q,
            selected_col=selected_col,
            page=page,
            page_size=page_size,
            fts_enabled=bool(current_app.config.get("FTS_ENABLED")),
        )

        out_caps: list[dict[str, Any]] = []
        for cap in captures:
            citation = citation_fields_from_meta_json(cap.get("meta_json"))
            out_caps.append(
                {
                    "id": cap.get("id"),
                    "title": cap.get("title"),
                    "url": cap.get("url"),
                    "doi": cap.get("doi"),
                    "year": cap.get("year"),
                    "container_title": cap.get("container_title"),
                    "authors_short": citation.get("authors_short") or "",
                    "abstract_snip": citation.get("abstract_snip") or "",
                }
            )

        return jsonify(
            {
                "captures": out_caps,
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_more": has_more,
            }
        )
