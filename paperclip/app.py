from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from .db import close_db, get_db, init_db, rows_to_dicts
from .export import captures_to_bibtex, captures_to_ris
from .ingest import ingest_capture


_ALLOWED_ARTIFACTS = {"page.html", "content.html", "raw.json", "reduced.json"}


def _repo_root() -> Path:
    # paperclip/app.py -> paperclip/ -> repo root
    return Path(__file__).resolve().parents[1]


def _ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def _corsify(resp: Response) -> Response:
    # For extension -> localhost API calls.
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return resp


def _parse_int(s: str | None, default: int) -> int:
    try:
        return int(s) if s is not None else default
    except Exception:
        return default


def _tokenize_for_fts(q: str) -> str:
    # Turn arbitrary user input into a safe-ish MATCH query:
    # tokens => "tok1* tok2*"
    toks = re.findall(r"[A-Za-z0-9_]+", (q or "").lower())
    toks = [t for t in toks if t]
    return " ".join([t + "*" for t in toks])


def create_app(config: dict[str, Any] | None = None) -> Flask:
    cfg = config or {}

    root = _repo_root()
    data_dir = Path(cfg.get("DATA_DIR") or (root / "data")).resolve()
    db_path = Path(cfg.get("DB_PATH") or (data_dir / "db.sqlite3")).resolve()
    artifacts_dir = Path(cfg.get("ARTIFACTS_DIR") or (data_dir / "artifacts")).resolve()

    _ensure_dirs(data_dir, artifacts_dir)

    fts_enabled = init_db(db_path)

    app = Flask(
        __name__,
        static_folder=str(root / "static"),
        template_folder=str(root / "templates"),
    )
    app.config.update(
        SECRET_KEY=cfg.get("SECRET_KEY") or "paperclip-dev",
        DATA_DIR=data_dir,
        DB_PATH=db_path,
        ARTIFACTS_DIR=artifacts_dir,
        FTS_ENABLED=fts_enabled,
        MAX_CONTENT_LENGTH=cfg.get("MAX_CONTENT_LENGTH") or (25 * 1024 * 1024),  # 25MB
    )

    app.teardown_appcontext(close_db)

    # ----------------------------- Basic pages -----------------------------
    @app.get("/")
    def home():
        return redirect(url_for("library"))

    @app.get("/library/")
    def library():
        db = get_db()
        q = (request.args.get("q") or "").strip()
        col = (request.args.get("col") or "").strip()
        page = _parse_int(request.args.get("page"), 1)
        page_size = 50
        offset = max(0, (page - 1) * page_size)

        collections = rows_to_dicts(
            db.execute(
                """
                SELECT c.id, c.name, COUNT(ci.capture_id) AS count
                FROM collections c
                LEFT JOIN collection_items ci ON ci.collection_id = c.id
                GROUP BY c.id
                ORDER BY c.name COLLATE NOCASE ASC
                """
            ).fetchall()
        )

        # Query captures with optional filters
        params: list[Any] = []
        where: list[str] = []

        join = ""
        if col:
            join += " JOIN collection_items ci ON ci.capture_id = cap.id "
            where.append("ci.collection_id = ?")
            params.append(_parse_int(col, -1))

        fts = bool(app.config["FTS_ENABLED"])
        if q and fts:
            fts_q = _tokenize_for_fts(q)
            if fts_q:
                join = " JOIN capture_fts fts ON fts.capture_id = cap.id " + join
                where.append("capture_fts MATCH ?")
                params.append(fts_q)

        # total count
        sql_total = "SELECT COUNT(1) AS n FROM captures cap " + join
        if where:
            sql_total += " WHERE " + " AND ".join(where)
        total = db.execute(sql_total, tuple(params)).fetchone()["n"]

        # rows
        sql_rows = (
            """
            SELECT cap.id, cap.title, cap.url, cap.doi, cap.year, cap.container_title, cap.updated_at
            FROM captures cap
        """
            + join
        )
        if where:
            sql_rows += " WHERE " + " AND ".join(where)

        if q and fts:
            # FTS order (best effort)
            sql_rows += " ORDER BY bm25(capture_fts), cap.updated_at DESC "
        else:
            sql_rows += " ORDER BY cap.updated_at DESC "

        sql_rows += " LIMIT ? OFFSET ? "
        params_rows = params + [page_size, offset]

        captures = rows_to_dicts(db.execute(sql_rows, tuple(params_rows)).fetchall())

        # If FTS isn't enabled, fall back to a basic LIKE filter for q
        # (only when q is set and FTS isn't active)
        if q and not fts:
            qlike = f"%{q}%"
            # rerun with LIKE
            params2: list[Any] = []
            join2 = ""
            where2: list[str] = []
            if col:
                join2 += " JOIN collection_items ci ON ci.capture_id = cap.id "
                where2.append("ci.collection_id = ?")
                params2.append(_parse_int(col, -1))
            where2.append(
                "(cap.title LIKE ? OR cap.url LIKE ? OR cap.doi LIKE ? OR EXISTS (SELECT 1 FROM capture_text t WHERE t.capture_id=cap.id AND t.content_text LIKE ?))"
            )
            params2.extend([qlike, qlike, qlike, qlike])

            total = db.execute(
                "SELECT COUNT(1) AS n FROM captures cap "
                + join2
                + " WHERE "
                + " AND ".join(where2),
                tuple(params2),
            ).fetchone()["n"]

            captures = rows_to_dicts(
                db.execute(
                    """
                    SELECT cap.id, cap.title, cap.url, cap.doi, cap.year, cap.container_title, cap.updated_at
                    FROM captures cap
                    """
                    + join2
                    + " WHERE "
                    + " AND ".join(where2)
                    + " ORDER BY cap.updated_at DESC LIMIT ? OFFSET ?",
                    tuple(params2 + [page_size, offset]),
                ).fetchall()
            )

        return render_template(
            "library.html",
            q=q,
            selected_col=col,
            collections=collections,
            captures=captures,
            page=page,
            page_size=page_size,
            total=total,
        )

    @app.get("/captures/<capture_id>/")
    def capture_detail(capture_id: str):
        db = get_db()
        cap = db.execute(
            "SELECT * FROM captures WHERE id = ?", (capture_id,)
        ).fetchone()
        if not cap:
            abort(404)

        meta_json = cap["meta_json"] or "{}"
        try:
            meta = json.loads(meta_json)
        except Exception:
            meta = {}

        collections = rows_to_dicts(
            db.execute(
                """
                SELECT c.id, c.name,
                  EXISTS(
                    SELECT 1 FROM collection_items ci
                    WHERE ci.collection_id = c.id AND ci.capture_id = ?
                  ) AS has_it
                FROM collections c
                ORDER BY c.name COLLATE NOCASE ASC
                """,
                (capture_id,),
            ).fetchall()
        )

        artifacts_dir = Path(app.config["ARTIFACTS_DIR"]) / capture_id
        artifact_links: list[dict[str, str]] = []
        for name in sorted(_ALLOWED_ARTIFACTS):
            p = artifacts_dir / name
            if p.exists():
                artifact_links.append(
                    {
                        "name": name,
                        "href": url_for(
                            "artifact_download", capture_id=capture_id, filename=name
                        ),
                    }
                )

        cap_dict = {k: cap[k] for k in cap.keys()}
        return render_template(
            "capture.html",
            capture=cap_dict,
            meta=meta,
            collections=collections,
            artifact_links=artifact_links,
        )

    @app.post("/captures/<capture_id>/collections/")
    def capture_set_collections(capture_id: str):
        db = get_db()
        cap = db.execute(
            "SELECT id FROM captures WHERE id = ?", (capture_id,)
        ).fetchone()
        if not cap:
            abort(404)

        selected = request.form.getlist("collection_ids")
        selected_ids: set[int] = set()
        for s in selected:
            try:
                selected_ids.add(int(s))
            except Exception:
                continue

        # Replace membership
        db.execute("DELETE FROM collection_items WHERE capture_id = ?", (capture_id,))
        for cid in sorted(selected_ids):
            db.execute(
                "INSERT OR IGNORE INTO collection_items (collection_id, capture_id, added_at) VALUES (?, ?, datetime('now'))",
                (cid, capture_id),
            )
        db.commit()

        flash("Collections updated.")
        return redirect(url_for("capture_detail", capture_id=capture_id))

    @app.get("/collections/")
    def collections_page():
        db = get_db()
        collections = rows_to_dicts(
            db.execute(
                """
                SELECT c.id, c.name, COUNT(ci.capture_id) AS count
                FROM collections c
                LEFT JOIN collection_items ci ON ci.collection_id = c.id
                GROUP BY c.id
                ORDER BY c.name COLLATE NOCASE ASC
                """
            ).fetchall()
        )
        return render_template("collections.html", collections=collections)

    @app.post("/collections/create/")
    def collections_create():
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Collection name is required.")
            return redirect(url_for("collections_page"))

        db = get_db()
        try:
            db.execute(
                "INSERT INTO collections (name, created_at) VALUES (?, datetime('now'))",
                (name,),
            )
            db.commit()
            flash("Collection created.")
        except Exception:
            db.rollback()
            flash("Collection name already exists.")
        return redirect(url_for("collections_page"))

    @app.post("/collections/<int:collection_id>/rename/")
    def collections_rename(collection_id: int):
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("New name is required.")
            return redirect(url_for("collections_page"))

        db = get_db()
        try:
            db.execute(
                "UPDATE collections SET name = ? WHERE id = ?", (name, collection_id)
            )
            db.commit()
            flash("Collection renamed.")
        except Exception:
            db.rollback()
            flash("Rename failed (name might already exist).")
        return redirect(url_for("collections_page"))

    @app.post("/collections/<int:collection_id>/delete/")
    def collections_delete(collection_id: int):
        db = get_db()
        db.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        db.commit()
        flash("Collection deleted.")
        return redirect(url_for("collections_page"))

    # ----------------------------- Artifact files -----------------------------
    @app.get("/captures/<capture_id>/artifacts/<path:filename>")
    def artifact_download(capture_id: str, filename: str):
        if filename not in _ALLOWED_ARTIFACTS:
            abort(404)
        p = Path(app.config["ARTIFACTS_DIR"]) / capture_id / filename
        if not p.exists():
            abort(404)
        return send_file(p, as_attachment=True)

    # ----------------------------- Exports -----------------------------
    def _fetch_export_rows(col: int | None) -> list[dict[str, Any]]:
        db = get_db()
        if col is None:
            rows = db.execute(
                """
                SELECT id, title, url, doi, year, container_title, meta_json
                FROM captures
                ORDER BY updated_at DESC
                """
            ).fetchall()
            return rows_to_dicts(rows)

        rows = db.execute(
            """
            SELECT cap.id, cap.title, cap.url, cap.doi, cap.year, cap.container_title, cap.meta_json
            FROM captures cap
            JOIN collection_items ci ON ci.capture_id = cap.id
            WHERE ci.collection_id = ?
            ORDER BY cap.updated_at DESC
            """,
            (col,),
        ).fetchall()
        return rows_to_dicts(rows)

    @app.get("/exports/bibtex/")
    def export_bibtex():
        col_s = (request.args.get("col") or "").strip()
        col = None
        if col_s:
            try:
                col = int(col_s)
            except Exception:
                col = None

        rows = _fetch_export_rows(col)
        out = captures_to_bibtex(rows)
        filename = "paperclip.bib" if col is None else f"paperclip-col-{col}.bib"
        resp = Response(out, mimetype="application/x-bibtex; charset=utf-8")
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @app.get("/exports/ris/")
    def export_ris():
        col_s = (request.args.get("col") or "").strip()
        col = None
        if col_s:
            try:
                col = int(col_s)
            except Exception:
                col = None

        rows = _fetch_export_rows(col)
        out = captures_to_ris(rows)
        filename = "paperclip.ris" if col is None else f"paperclip-col-{col}.ris"
        resp = Response(
            out, mimetype="application/x-research-info-systems; charset=utf-8"
        )
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @app.get("/captures/<capture_id>/bibtex/")
    def export_capture_bibtex(capture_id: str):
        db = get_db()
        row = db.execute(
            "SELECT id, title, url, doi, year, container_title, meta_json FROM captures WHERE id = ?",
            (capture_id,),
        ).fetchone()
        if not row:
            abort(404)
        out = captures_to_bibtex([dict(row)])
        resp = Response(out, mimetype="application/x-bibtex; charset=utf-8")
        resp.headers["Content-Disposition"] = (
            f'attachment; filename="paperclip-{capture_id[:8]}.bib"'
        )
        return resp

    @app.get("/captures/<capture_id>/ris/")
    def export_capture_ris(capture_id: str):
        db = get_db()
        row = db.execute(
            "SELECT id, title, url, doi, year, container_title, meta_json FROM captures WHERE id = ?",
            (capture_id,),
        ).fetchone()
        if not row:
            abort(404)
        out = captures_to_ris([dict(row)])
        resp = Response(
            out, mimetype="application/x-research-info-systems; charset=utf-8"
        )
        resp.headers["Content-Disposition"] = (
            f'attachment; filename="paperclip-{capture_id[:8]}.ris"'
        )
        return resp

    # ----------------------------- API -----------------------------
    @app.get("/api/healthz/")
    def api_healthz():
        resp = jsonify({"ok": True})
        return _corsify(resp)

    @app.route("/api/captures/", methods=["OPTIONS"])
    def api_captures_options():
        return _corsify(Response("", status=204))

    @app.get("/api/captures/")
    def api_captures_list():
        db = get_db()
        page = _parse_int(request.args.get("page"), 1)
        page_size = _parse_int(request.args.get("page_size"), 50)
        page = max(1, page)
        page_size = min(max(1, page_size), 200)
        offset = (page - 1) * page_size

        rows = db.execute(
            """
            SELECT id, title, url
            FROM captures
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()

        total = db.execute("SELECT COUNT(1) AS n FROM captures").fetchone()["n"]
        resp = jsonify(
            {
                "count": total,
                "page": page,
                "page_size": page_size,
                "results": rows_to_dicts(rows),
            }
        )
        return _corsify(resp)

    @app.get("/api/captures/<capture_id>/")
    def api_captures_get(capture_id: str):
        db = get_db()
        cap = db.execute(
            "SELECT id, title, url, doi, year, meta_json FROM captures WHERE id = ?",
            (capture_id,),
        ).fetchone()
        if not cap:
            resp = jsonify({"detail": "Not found"})
            resp.status_code = 404
            return _corsify(resp)

        # Try reduced.json if present
        reduced = None
        p = Path(app.config["ARTIFACTS_DIR"]) / capture_id / "reduced.json"
        if p.exists():
            try:
                reduced = json.loads(
                    p.read_text(encoding="utf-8", errors="ignore") or "null"
                )
            except Exception:
                reduced = None

        meta = {}
        try:
            meta = json.loads(cap["meta_json"] or "{}")
        except Exception:
            meta = {}

        resp = jsonify(
            {
                "id": cap["id"],
                "title": cap["title"],
                "url": cap["url"],
                "doi": cap["doi"],
                "year": cap["year"],
                "meta": meta,
                "reduced": reduced,
            }
        )
        return _corsify(resp)

    @app.post("/api/captures/")
    def api_captures_create():
        try:
            payload = request.get_json(force=True)
        except Exception:
            payload = None

        if not isinstance(payload, dict):
            resp = jsonify({"detail": "Invalid JSON body"})
            resp.status_code = 400
            return _corsify(resp)

        db = get_db()
        try:
            res = ingest_capture(
                payload=payload,
                db=db,
                artifacts_root=Path(app.config["ARTIFACTS_DIR"]),
                fts_enabled=bool(app.config["FTS_ENABLED"]),
            )
        except Exception as e:
            resp = jsonify({"detail": str(e)})
            resp.status_code = 400
            return _corsify(resp)

        resp = jsonify(
            {
                "capture_id": res.capture_id,
                "created": res.created,
                "summary": res.summary,
            }
        )
        resp.status_code = 201 if res.created else 200
        return _corsify(resp)

    # For any /api response, ensure CORS headers even if we forgot a route wrapper.
    @app.after_request
    def _after(resp: Response):
        if request.path.startswith("/api/"):
            return _corsify(resp)
        return resp

    return app
