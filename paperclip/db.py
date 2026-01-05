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
  url_hash       TEXT NOT NULL UNIQUE,

  title          TEXT NOT NULL,
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


FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS capture_fts USING fts5(
  capture_id UNINDEXED,
  title,
  content_text
);
"""


def init_db(db_path: Path) -> bool:
    """
    Initialize the SQLite DB if needed.
    Returns True if FTS was created/enabled, False otherwise.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.executescript(SCHEMA_SQL)

        # Prefer DOI-based de-dupe when DOI exists, but keep startup resilient if
        # an existing DB already contains duplicate DOIs.
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_captures_doi ON captures(doi) WHERE doi <> ''"
            )
        except sqlite3.IntegrityError:
            # Existing duplicates; keep running (app-level de-dupe will still help).
            pass

        fts_enabled = True
        try:
            conn.executescript(FTS_SQL)
        except sqlite3.OperationalError:
            # Some SQLite builds might not have FTS5. We can still operate without it.
            fts_enabled = False

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
