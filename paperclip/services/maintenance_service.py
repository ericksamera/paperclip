from __future__ import annotations

from typing import Any


def rebuild_fts(db) -> dict[str, Any]:
    """
    Rebuild capture_fts from captures + capture_text.

    Uses captures.rowid as the stable key that matches capture_fts.rowid.

    Returns small stats payload. Raises sqlite3.OperationalError if FTS isn't available.
    """
    cap_count = int(db.execute("SELECT COUNT(1) AS n FROM captures").fetchone()["n"])

    db.execute("DELETE FROM capture_fts")
    db.execute(
        """
        INSERT INTO capture_fts(rowid, title, content_text)
        SELECT
          cap.rowid AS rowid,
          COALESCE(cap.title, '') AS title,
          COALESCE(ct.content_text, '') AS content_text
        FROM captures cap
        LEFT JOIN capture_text ct
          ON ct.capture_id = cap.id
        """
    )
    fts_rows = int(db.execute("SELECT COUNT(1) AS n FROM capture_fts").fetchone()["n"])

    return {
        "captures": cap_count,
        "fts_rows": fts_rows,
    }


def verify_fts(db) -> dict[str, Any]:
    """
    Verify that capture_fts is in sync with captures.

    Returns:
      {
        "captures": int,
        "fts_rows": int,
        "missing_rows": int,   # captures without an FTS row
        "extra_rows": int,     # FTS rows without a captures row
        "ok": bool,
      }

    Raises sqlite3.OperationalError if FTS isn't available.
    """
    captures = int(db.execute("SELECT COUNT(1) AS n FROM captures").fetchone()["n"])
    fts_rows = int(db.execute("SELECT COUNT(1) AS n FROM capture_fts").fetchone()["n"])

    # Missing FTS rows for existing captures
    missing_rows = int(
        db.execute(
            """
            SELECT COUNT(1) AS n
            FROM captures cap
            LEFT JOIN capture_fts fts
              ON fts.rowid = cap.rowid
            WHERE fts.rowid IS NULL
            """
        ).fetchone()["n"]
    )

    # Extra FTS rows whose rowid no longer exists in captures
    extra_rows = int(
        db.execute(
            """
            SELECT COUNT(1) AS n
            FROM capture_fts fts
            LEFT JOIN captures cap
              ON cap.rowid = fts.rowid
            WHERE cap.rowid IS NULL
            """
        ).fetchone()["n"]
    )

    ok = (missing_rows == 0) and (extra_rows == 0) and (captures == fts_rows)

    return {
        "captures": captures,
        "fts_rows": fts_rows,
        "missing_rows": missing_rows,
        "extra_rows": extra_rows,
        "ok": bool(ok),
    }
