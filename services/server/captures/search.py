# services/server/captures/search.py
from __future__ import annotations
import json
from typing import Iterable, List
from django.db import connection as _default_connection
from paperclip.artifacts import artifact_path

_FTS = "capture_fts"

def ensure_fts(conn=None) -> None:
    """
    Create the SQLite FTS5 table if it doesn't exist.
    - No-ops on non-SQLite backends.
    - Idempotent and safe to call often.
    """
    conn = conn or _default_connection
    try:
        if getattr(conn, "vendor", "") != "sqlite":
            return
        with conn.cursor() as c:
            c.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {_FTS} "
                "USING fts5(pk UNINDEXED, title, body, url, doi, tokenize='porter');"
            )
    except Exception:
        # Some SQLite builds may lack FTS5; treat as best-effort
        pass

def _preview_text(capture_id: str) -> str:
    try:
        p = artifact_path(capture_id, "view.json")
        if p.exists():
            view = json.loads(p.read_text("utf-8"))
            paras = (view.get("sections") or {}).get("abstract_or_body") or []
            return " ".join(paras[:50])
    except Exception:
        pass
    return ""

def _build_row(c) -> tuple[str, str, str, str, str]:
    meta = c.meta or {}
    csl = c.csl or {}
    bits = []
    kw = meta.get("keywords") or []
    if isinstance(kw, list):
        bits += kw
    if meta.get("abstract"):
        bits.append(str(meta.get("abstract")))
    elif isinstance(csl, dict) and csl.get("abstract"):
        bits.append(str(csl.get("abstract")))
    bits.append(_preview_text(str(c.id)))
    body = " ".join([b for b in bits if b])
    return (str(c.id), (c.title or ""), body, (c.url or ""), (c.doi or ""))

def upsert_capture(capture) -> None:
    """Insert/replace a row for a capture."""
    ensure_fts()
    from django.db import connection as conn
    with conn.cursor() as c:
        pk, title, body, url, doi = _build_row(capture)
        c.execute(
            f"INSERT INTO {_FTS}(pk,title,body,url,doi) VALUES (?,?,?,?,?) "
            "ON CONFLICT(pk) DO UPDATE SET "
            "title=excluded.title, body=excluded.body, url=excluded.url, doi=excluded.doi",
            [pk, title, body, url, doi],
        )

def delete_capture(capture_id: str) -> None:
    ensure_fts()
    from django.db import connection as conn
    with conn.cursor() as c:
        c.execute(f"DELETE FROM {_FTS} WHERE pk = ?", [str(capture_id)])

def search_ids(q: str, limit: int = 2000) -> List[str]:
    """Return capture PKs ranked by bm25 (SQLite FTS5)."""
    if not q.strip():
        return []
    ensure_fts()
    from django.db import connection as conn
    with conn.cursor() as c:
        c.execute(
            f"SELECT pk FROM {_FTS} WHERE {_FTS} MATCH ? "
            f"ORDER BY bm25({_FTS}) LIMIT ?",
            [q, limit],
        )
        return [row[0] for row in c.fetchall()]
