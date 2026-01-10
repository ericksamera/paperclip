from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from flask import current_app, g


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS captures (
  id             TEXT PRIMARY KEY,
  url            TEXT NOT NULL,
  url_canon      TEXT NOT NULL,
  url_hash       TEXT NOT NULL,
  title          TEXT NOT NULL DEFAULT '',
  doi            TEXT NOT NULL DEFAULT '',
  year           INTEGER,
  container_title TEXT NOT NULL DEFAULT '',
  meta_json      TEXT NOT NULL DEFAULT '{}',
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capture_text (
  capture_id   TEXT PRIMARY KEY REFERENCES captures(id) ON DELETE CASCADE,
  content_text TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS collections (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL UNIQUE,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_items (
  collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  capture_id    TEXT NOT NULL REFERENCES captures(id) ON DELETE CASCADE,
  added_at      TEXT NOT NULL,
  PRIMARY KEY (collection_id, capture_id)
);

CREATE INDEX IF NOT EXISTS idx_captures_updated_at ON captures(updated_at);
CREATE INDEX IF NOT EXISTS idx_captures_doi ON captures(doi);
CREATE INDEX IF NOT EXISTS idx_collection_items_capture ON collection_items(capture_id);
"""


# NOTE:
# We intentionally use the FTS rowid (INTEGER) and store only the indexed columns.
# We map capture_id <-> rowid via the captures table rowid:
#   - upsert: INSERT ... (rowid, title, content_text) ... ON CONFLICT(rowid) DO UPDATE ...
#   - query:  cap.rowid IN (SELECT rowid FROM capture_fts WHERE capture_fts MATCH ?)
FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS capture_fts USING fts5(
  title,
  content_text
);
"""


def init_db(db_path: Path) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA_SQL)

        # Lightweight migration runner (idempotent and safe to extend).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              id         TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL
            );
            """
        )

        def _applied(mid: str) -> bool:
            row = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE id = ? LIMIT 1", (mid,)
            ).fetchone()
            return row is not None

        def _mark(mid: str) -> None:
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (id, applied_at) VALUES (?, datetime('now'))",
                (mid,),
            )

        # Migration: prefer DOI-based de-dupe when DOI exists.
        mid = "2026-01-09_ux_captures_doi"
        if not _applied(mid):
            try:
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_captures_doi ON captures(doi) WHERE doi <> ''"
                )
            except sqlite3.IntegrityError:
                # Existing duplicates; keep running (app-level de-dupe will still help).
                pass
            _mark(mid)

        # Try to enable FTS; app still works without it.
        fts_enabled = True
        try:
            conn.executescript(FTS_SQL)
        except sqlite3.OperationalError:
            # Some SQLite builds might not have FTS5. We can still operate without it.
            fts_enabled = False

        # Migration: rebuild capture_fts to the rowid-keyed schema (safe, idempotent).
        # Older versions may have had a capture_id column; we drop and recreate.
        mid = "2026-01-10_capture_fts_rowid_schema"
        if fts_enabled and not _applied(mid):
            try:
                conn.execute("DROP TABLE IF EXISTS capture_fts;")
                conn.executescript(FTS_SQL)
            except Exception:
                # Best effort: if anything fails, we keep running without hard-failing startup.
                pass
            _mark(mid)

        conn.commit()
        return fts_enabled
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db_path = current_app.config["DB_PATH"]
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        g.db = conn
    return g.db


def close_db(_err: Any = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({k: r[k] for k in r.keys()})
    return out
