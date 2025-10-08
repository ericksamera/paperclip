from __future__ import annotations

import re
from contextlib import contextmanager, suppress
from typing import Any, Mapping

from django.db import connection as _default_connection

from captures.keywords import split_keywords
from captures.text_assembly import assemble_body_text
from captures.types import CSL

_FTS = "capture_fts"


@contextmanager
def _no_debug_cursor(conn):
    prev = getattr(conn, "use_debug_cursor", False)
    try:
        with suppress(Exception):
            conn.use_debug_cursor = False
        yield
    finally:
        with suppress(Exception):
            conn.use_debug_cursor = prev


def _sql_literal(s: str) -> str:
    """SQLite single-quoted string literal (escape single quotes)."""
    return "'" + (s or "").replace("'", "''") + "'"


def ensure_fts(conn=None) -> None:
    """
    Create the SQLite FTS5 table if it doesn't exist.
    """
    conn = conn or _default_connection
    if getattr(conn, "vendor", "") != "sqlite":
        return
    with _no_debug_cursor(conn), conn.cursor() as c:
        c.execute(
            f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {_FTS} USING fts5(
                    pk UNINDEXED,
                    title,
                    body,
                    url,
                    doi,
                    tokenize='unicode61 remove_diacritics 2'
                )
                """
        )


def reindex_all() -> None:
    """Drop all FTS rows and repopulate from captures."""
    ensure_fts()
    from django.db import connection as conn
    from captures.models import Capture

    with _no_debug_cursor(conn), conn.cursor() as c:
        c.execute(f"DELETE FROM {_FTS}")
    for cap in Capture.objects.all().iterator():
        upsert_capture(cap)


def delete_capture(capture_id: str) -> None:
    ensure_fts()
    from django.db import connection as conn

    with _no_debug_cursor(conn), conn.cursor() as c:
        c.execute(f"DELETE FROM {_FTS} WHERE pk = {_sql_literal(str(capture_id))}")


def upsert_capture(capture) -> None:
    """
    Insert/replace a row for a capture.
    NOTE: SQLite FTS5 does not support UPSERT. Emulate with DELETE + INSERT.
    """
    ensure_fts()
    from django.db import connection as conn

    with _no_debug_cursor(conn), conn.cursor() as c:
        pk, title, body, url, doi = _build_row(capture)
        c.execute(f"DELETE FROM {_FTS} WHERE pk = {_sql_literal(pk)}")
        values = ",".join(
            [
                _sql_literal(pk),
                _sql_literal(title),
                _sql_literal(body),
                _sql_literal(url),
                _sql_literal(doi),
            ]
        )
        c.execute(f"INSERT INTO {_FTS}(pk,title,body,url,doi) VALUES ({values})")


def _build_row(c) -> tuple[str, str, str, str, str]:
    meta: Mapping[str, Any] = c.meta or {}
    csl: CSL | Mapping[str, Any] = c.csl or {}

    # Build the "body" = meta/csl + reduced-view preview + keywords
    kw = meta.get("keywords") or []
    if isinstance(kw, str):
        kw = split_keywords(kw)

    body = assemble_body_text(
        capture_id=str(c.id),
        meta=meta,
        csl=csl,
        keywords=kw if isinstance(kw, (list, tuple)) else [],
    )
    return (str(c.id), (c.title or ""), body, (c.url or ""), (c.doi or ""))


def _fts_sanitize_query(q: str) -> str:
    """
    Make user text safe for the FTS query grammar.
    - Hyphens are boolean NOT in FTS5. Quote any token with '-' or that starts with '-'.
    - Quote tokens with ':' (avoid column-spec parsing like doi:10.1101/...).
    - Preserve explicit AND/OR/NOT.
    - Keep existing double-quoted phrases intact.
    """
    q = (q or "").strip()
    if not q:
        return q
    q = q.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    tokens = re.findall(r'"[^"]+"|\S+', q)
    out: list[str] = []
    for t in tokens:
        if t.startswith('"') and t.endswith('"') and len(t) >= 2:
            out.append(t)
            continue
        if t.upper() in {"AND", "OR", "NOT"}:
            out.append(t.upper())
            continue
        needs_quotes = t.startswith("-") or ("-" in t) or (":" in t)
        out.append('"' + t.replace('"', '""') + '"' if needs_quotes else t)
    return " ".join(out)


def search_ids(q: str, limit: int = 2000) -> list[str]:
    """
    Return capture PKs ranked by bm25 (SQLite FTS5).
    All SQL is executed WITHOUT params to keep Django's DEBUG logging happy.
    """
    q = (q or "").strip()
    if not q:
        return []
    ensure_fts()
    from django.db import connection as conn

    lim = max(1, int(limit))

    def _exec(query_text: str) -> list[str]:
        qlit = _sql_literal(query_text)
        sql = (
            f"SELECT pk FROM {_FTS} "
            f"WHERE {_FTS} MATCH {qlit} "
            f"ORDER BY bm25({_FTS}) LIMIT {lim}"
        )
        with conn.cursor() as c:
            c.execute(sql)
            return [row[0] for row in c.fetchall()]

    try:
        return _exec(_fts_sanitize_query(q))
    except Exception:
        try:
            qtoks = ['"' + t.replace('"', '""') + '"' for t in re.findall(r"\S+", q)]
            return _exec(" ".join(qtoks))
        except Exception:
            safe_terms = re.findall(r"[A-Za-z0-9]+", q)
            return _exec(" ".join(safe_terms)) if safe_terms else []
