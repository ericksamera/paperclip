from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
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

_ALLOWED_ARTIFACTS = ("page.html", "content.html", "raw.json", "reduced.json")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_dirs(*dirs: Path) -> None:
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_int(v: str | None, default: int) -> int:
    try:
        return int(v) if v is not None else default
    except Exception:
        return default


def _safe_next(next_url: str | None) -> str:
    if not next_url:
        return url_for("library")
    s = next_url.strip()
    if not s.startswith("/") or s.startswith("//"):
        return url_for("library")
    return s


def _chunks(items: list[str], n: int) -> list[list[str]]:
    return [items[i : i + n] for i in range(0, len(items), n)]


def _normalize_authors(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, str):
        val = [val]
    if not isinstance(val, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for a in val:
        s = str(a).strip()
        if not s:
            continue
        k = s.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _normalize_abstract(val: Any) -> str:
    if val is None:
        return ""
    if not isinstance(val, str):
        val = str(val)
    return re.sub(r"\s+", " ", val).strip()


def _snip_text(s: str, max_len: int = 240) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if len(s) <= max_len:
        return s
    cut = s[: max_len - 1].rstrip()
    m = re.search(r"\s+\S*$", cut)
    if m and m.start() >= int(max_len * 0.6):
        cut = cut[: m.start()].rstrip()
    return cut + "…"


def _citation_fields_from_meta(meta: dict[str, Any]) -> dict[str, Any]:
    authors = _normalize_authors(meta.get("authors"))
    abstract = _normalize_abstract(meta.get("abstract"))
    return {
        "authors": authors,
        "authors_str": ", ".join(authors),
        "abstract": abstract,
        "abstract_snip": _snip_text(abstract, 240) if abstract else "",
    }


def _citation_fields_from_meta_json(meta_json: str | None) -> dict[str, Any]:
    try:
        meta = json.loads(meta_json or "{}")
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return _citation_fields_from_meta(meta)


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

    # Critical: db.py expects these keys
    app.config.update(
        DATA_DIR=data_dir,
        DB_PATH=db_path,
        ARTIFACTS_DIR=artifacts_dir,
        FTS_ENABLED=fts_enabled,
    )

    if "MAX_CONTENT_LENGTH" in cfg:
        app.config["MAX_CONTENT_LENGTH"] = cfg["MAX_CONTENT_LENGTH"]

    app.secret_key = cfg.get("SECRET_KEY") or "paperclip-dev"
    app.teardown_appcontext(close_db)

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

        total_all = db.execute("SELECT COUNT(1) AS n FROM captures").fetchone()["n"]

        join = ""
        where: list[str] = []
        params: list[Any] = []

        if col:
            join += " JOIN collection_items ci ON ci.capture_id = cap.id "
            where.append("ci.collection_id = ?")
            params.append(_parse_int(col, -1))

        if q:
            qlike = f"%{q}%"
            where.append(
                "(cap.title LIKE ? OR cap.url LIKE ? OR cap.doi LIKE ? "
                "OR cap.id IN (SELECT capture_id FROM capture_text WHERE content_text LIKE ?))"
            )
            params.extend([qlike, qlike, qlike, qlike])

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        total = db.execute(
            "SELECT COUNT(1) AS n FROM captures cap " + join + where_sql,
            tuple(params),
        ).fetchone()["n"]

        captures = rows_to_dicts(
            db.execute(
                """
                SELECT cap.id, cap.title, cap.url, cap.doi, cap.year, cap.container_title,
                       cap.updated_at, cap.meta_json
                FROM captures cap
                """
                + join
                + where_sql
                + " ORDER BY cap.updated_at DESC LIMIT ? OFFSET ?",
                tuple(params + [page_size, offset]),
            ).fetchall()
        )

        for cap in captures:
            citation = _citation_fields_from_meta_json(cap.get("meta_json"))
            cap["authors_str"] = citation.get("authors_str") or ""
            cap["abstract_snip"] = citation.get("abstract_snip") or ""
            cap.pop("meta_json", None)

        return render_template(
            "library.html",
            q=q,
            selected_col=col,
            collections=collections,
            captures=captures,
            page=page,
            page_size=page_size,
            total=total,
            total_all=total_all,
        )

    @app.get("/captures/<capture_id>/")
    def capture_detail(capture_id: str):
        db = get_db()
        cap = db.execute(
            "SELECT * FROM captures WHERE id = ?", (capture_id,)
        ).fetchone()
        if not cap:
            abort(404)

        cap_dict = {k: cap[k] for k in cap.keys()}

        meta_json = cap_dict.get("meta_json") or "{}"
        try:
            meta = json.loads(meta_json)
        except Exception:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}

        citation = _citation_fields_from_meta(meta)
        authors_str = citation.get("authors_str") or ""
        abstract = citation.get("abstract") or ""

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

        art_root = Path(app.config["ARTIFACTS_DIR"])
        art_dir = art_root / capture_id
        artifact_links: dict[str, str] = {}
        for name in _ALLOWED_ARTIFACTS:
            p = art_dir / name
            if p.exists():
                artifact_links[name] = url_for(
                    "artifact", capture_id=capture_id, name=name
                )

        return render_template(
            "capture.html",
            capture=cap_dict,
            meta=meta,
            collections=collections,
            artifact_links=artifact_links,
            authors_str=authors_str,
            abstract=abstract,
        )

    @app.post("/captures/<capture_id>/collections/")
    def capture_set_collections(capture_id: str):
        db = get_db()
        exists = db.execute(
            "SELECT 1 FROM captures WHERE id = ?", (capture_id,)
        ).fetchone()
        if not exists:
            abort(404)

        selected = request.form.getlist("collections")
        selected_ids = [_parse_int(x, -1) for x in selected if x.strip()]
        now = _utc_now_iso()

        db.execute("DELETE FROM collection_items WHERE capture_id = ?", (capture_id,))
        for cid in selected_ids:
            if cid > 0:
                db.execute(
                    """
                    INSERT OR IGNORE INTO collection_items (collection_id, capture_id, added_at)
                    VALUES (?, ?, ?)
                    """,
                    (cid, capture_id, now),
                )
        db.commit()

        flash("Updated collections.")
        return redirect(url_for("capture_detail", capture_id=capture_id))

    @app.get("/artifacts/<capture_id>/<name>/")
    def artifact(capture_id: str, name: str):
        if name not in _ALLOWED_ARTIFACTS:
            abort(404)
        p = Path(app.config["ARTIFACTS_DIR"]) / capture_id / name
        if not p.exists():
            abort(404)
        return send_file(p)

    # --- Bulk actions used by UI + tests ---

    @app.post("/captures/delete/")
    def captures_delete():
        capture_ids = request.form.getlist("capture_ids")
        next_url = _safe_next(request.form.get("next"))

        capture_ids = [c for c in capture_ids if c]
        if not capture_ids:
            flash("No captures selected.")
            return redirect(next_url)

        db = get_db()
        fts = bool(app.config.get("FTS_ENABLED"))

        for chunk in _chunks(capture_ids, 200):
            qmarks = ",".join("?" for _ in chunk)
            db.execute(f"DELETE FROM captures WHERE id IN ({qmarks})", tuple(chunk))
            if fts:
                db.execute(
                    f"DELETE FROM capture_fts WHERE capture_id IN ({qmarks})",
                    tuple(chunk),
                )
        db.commit()

        art_root = Path(app.config["ARTIFACTS_DIR"])
        for cid in capture_ids:
            d = art_root / cid
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

        flash(f"Deleted {len(capture_ids)} captures.")
        return redirect(next_url)

    @app.post("/captures/collections/add/")
    def captures_collections_add():
        capture_ids = [c for c in request.form.getlist("capture_ids") if c]
        collection_id = _parse_int(request.form.get("collection_id"), -1)
        next_url = _safe_next(request.form.get("next"))

        if not capture_ids or collection_id <= 0:
            flash("Select captures and a collection.")
            return redirect(next_url)

        db = get_db()
        now = _utc_now_iso()
        for cid in capture_ids:
            db.execute(
                """
                INSERT OR IGNORE INTO collection_items (collection_id, capture_id, added_at)
                VALUES (?, ?, ?)
                """,
                (collection_id, cid, now),
            )
        db.commit()

        flash(f"Added {len(capture_ids)} captures to collection.")
        return redirect(next_url)

    @app.post("/captures/collections/remove/")
    def captures_collections_remove():
        capture_ids = [c for c in request.form.getlist("capture_ids") if c]
        collection_id = _parse_int(request.form.get("collection_id"), -1)
        next_url = _safe_next(request.form.get("next"))

        if not capture_ids or collection_id <= 0:
            flash("Select captures and a collection.")
            return redirect(next_url)

        db = get_db()
        for chunk in _chunks(capture_ids, 200):
            qmarks = ",".join("?" for _ in chunk)
            db.execute(
                f"DELETE FROM collection_items WHERE collection_id = ? AND capture_id IN ({qmarks})",
                tuple([collection_id] + chunk),
            )
        db.commit()

        flash(f"Removed {len(capture_ids)} captures from collection.")
        return redirect(next_url)

    # --- Collections UI ---

    @app.get("/collections/")
    def collections_page():
        db = get_db()
        cols = rows_to_dicts(
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
        return render_template("collections.html", collections=cols)

    @app.post("/collections/create/")
    def collections_create():
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name required.")
            return redirect(url_for("collections_page"))

        db = get_db()
        db.execute(
            "INSERT INTO collections (name, created_at) VALUES (?, ?)",
            (name, _utc_now_iso()),
        )
        db.commit()
        flash("Created collection.")
        return redirect(url_for("collections_page"))

    @app.post("/collections/<int:collection_id>/rename/")
    def collections_rename(collection_id: int):
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name required.")
            return redirect(url_for("collections_page"))

        db = get_db()
        db.execute(
            "UPDATE collections SET name = ? WHERE id = ?", (name, collection_id)
        )
        db.commit()
        flash("Renamed collection.")
        return redirect(url_for("collections_page"))

    @app.post("/collections/<int:collection_id>/delete/")
    def collections_delete(collection_id: int):
        db = get_db()
        db.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        db.commit()
        flash("Deleted collection.")
        return redirect(url_for("collections_page"))

    # --- Exports ---

    def _captures_for_export(
        capture_ids: list[str] | None = None, collection_id: int | None = None
    ) -> list[dict[str, Any]]:
        db = get_db()
        params: list[Any] = []
        where: list[str] = []
        join = ""

        if collection_id:
            join += " JOIN collection_items ci ON ci.capture_id = cap.id "
            where.append("ci.collection_id = ?")
            params.append(collection_id)

        if capture_ids:
            qmarks = ",".join("?" for _ in capture_ids)
            where.append(f"cap.id IN ({qmarks})")
            params.extend(capture_ids)

        sql = (
            """
            SELECT cap.id, cap.title, cap.url, cap.doi, cap.year, cap.container_title, cap.meta_json
            FROM captures cap
        """
            + join
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY cap.updated_at DESC"

        return rows_to_dicts(db.execute(sql, tuple(params)).fetchall())

    @app.get("/exports/bibtex/")
    def export_bibtex():
        col = _parse_int(request.args.get("col"), 0)
        rows = _captures_for_export(collection_id=col if col > 0 else None)
        bib = captures_to_bibtex(rows)
        return Response(
            bib,
            mimetype="application/x-bibtex; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="paperclip.bib"'},
        )

    @app.get("/exports/ris/")
    def export_ris():
        col = _parse_int(request.args.get("col"), 0)
        rows = _captures_for_export(collection_id=col if col > 0 else None)
        ris = captures_to_ris(rows)
        return Response(
            ris,
            mimetype="application/x-research-info-systems; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="paperclip.ris"'},
        )

    @app.post("/exports/bibtex/selected/")
    def export_selected_bibtex():
        ids = [c for c in request.form.getlist("capture_ids") if c]
        rows = _captures_for_export(capture_ids=ids)
        bib = captures_to_bibtex(rows)
        return Response(
            bib,
            mimetype="application/x-bibtex; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="paperclip-selected.bib"'
            },
        )

    @app.post("/exports/ris/selected/")
    def export_selected_ris():
        ids = [c for c in request.form.getlist("capture_ids") if c]
        rows = _captures_for_export(capture_ids=ids)
        ris = captures_to_ris(rows)
        return Response(
            ris,
            mimetype="application/x-research-info-systems; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="paperclip-selected.ris"'
            },
        )

    @app.get("/captures/<capture_id>/exports/bibtex/")
    def export_capture_bibtex(capture_id: str):
        rows = _captures_for_export(capture_ids=[capture_id])
        bib = captures_to_bibtex(rows)
        return Response(
            bib,
            mimetype="application/x-bibtex; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="paperclip-{capture_id}.bib"'
            },
        )

    @app.get("/captures/<capture_id>/exports/ris/")
    def export_capture_ris(capture_id: str):
        rows = _captures_for_export(capture_ids=[capture_id])
        ris = captures_to_ris(rows)
        return Response(
            ris,
            mimetype="application/x-research-info-systems; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="paperclip-{capture_id}.ris"'
            },
        )

    # --- API ---

    @app.post("/api/captures/")
    def api_captures_create():
        payload = request.get_json(force=True, silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "Invalid JSON payload"}), 400

        db = get_db()
        try:
            result = ingest_capture(
                payload=payload,
                db=db,
                artifacts_root=Path(app.config["ARTIFACTS_DIR"]),
                fts_enabled=bool(app.config.get("FTS_ENABLED")),
            )
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        status = 201 if result.created else 200
        return (
            jsonify(
                {
                    "ok": True,
                    "capture_id": result.capture_id,
                    "created": result.created,
                    "summary": result.summary,
                }
            ),
            status,
        )

    @app.get("/api/captures/<capture_id>/")
    def api_captures_get(capture_id: str):
        db = get_db()
        cap = db.execute(
            "SELECT * FROM captures WHERE id = ?", (capture_id,)
        ).fetchone()
        if not cap:
            abort(404)
        cap_dict = {k: cap[k] for k in cap.keys()}
        return jsonify(cap_dict)

    return app
