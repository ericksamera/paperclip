from __future__ import annotations

from typing import Any

from ..db import rows_to_dicts


def _safe_int(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def get_collection_name(db, *, collection_id: int) -> str | None:
    row = db.execute(
        "SELECT name FROM collections WHERE id = ?", (collection_id,)
    ).fetchone()
    if not row:
        return None
    name = row["name"]
    return str(name) if name else None


def select_captures_for_export(
    db,
    *,
    capture_id: str | None,
    col: str | None,
) -> tuple[list[dict[str, Any]], str | None, int | None, str | None]:
    """
    Returns (captures, capture_id, col_id, col_name).
    """
    capture_id = (capture_id or "").strip() or None
    col = (col or "").strip() or None

    if capture_id:
        rows = db.execute(
            "SELECT * FROM captures WHERE id = ?", (capture_id,)
        ).fetchall()
        return rows_to_dicts(rows), capture_id, None, None

    col_id = _safe_int(col)
    if col_id and col_id > 0:
        rows = db.execute(
            """
            SELECT cap.*
            FROM captures cap
            JOIN collection_items ci ON ci.capture_id = cap.id
            WHERE ci.collection_id = ?
            ORDER BY cap.updated_at DESC
            """,
            (col_id,),
        ).fetchall()
        col_name = get_collection_name(db, collection_id=col_id)
        return rows_to_dicts(rows), None, col_id, col_name

    rows = db.execute("SELECT * FROM captures ORDER BY updated_at DESC").fetchall()
    return rows_to_dicts(rows), None, None, None


def select_captures_by_ids(db, *, capture_ids: list[str]) -> list[dict[str, Any]]:
    if not capture_ids:
        return []
    qmarks = ",".join(["?"] * len(capture_ids))
    rows = db.execute(
        f"SELECT * FROM captures WHERE id IN ({qmarks})",
        tuple(capture_ids),
    ).fetchall()
    return rows_to_dicts(rows)
