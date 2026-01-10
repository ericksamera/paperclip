from __future__ import annotations

from typing import Any

from ..db import rows_to_dicts


def get_collection_name(db, *, collection_id: int) -> str | None:
    row = db.execute(
        "SELECT name FROM collections WHERE id = ?", (collection_id,)
    ).fetchone()
    if not row:
        return None
    name = row["name"]
    return str(name) if name else None


def get_capture_by_id(db, *, capture_id: str) -> dict[str, Any] | None:
    row = db.execute("SELECT * FROM captures WHERE id = ?", (capture_id,)).fetchone()
    return dict(row) if row else None


def list_all_captures(db) -> list[dict[str, Any]]:
    rows = db.execute("SELECT * FROM captures ORDER BY updated_at DESC").fetchall()
    return rows_to_dicts(rows)


def list_captures_in_collection(db, *, collection_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT cap.*
        FROM captures cap
        JOIN collection_items ci ON ci.capture_id = cap.id
        WHERE ci.collection_id = ?
        ORDER BY cap.updated_at DESC
        """,
        (collection_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def select_captures_by_ids(db, *, capture_ids: list[str]) -> list[dict[str, Any]]:
    if not capture_ids:
        return []
    qmarks = ",".join(["?"] * len(capture_ids))
    rows = db.execute(
        f"SELECT * FROM captures WHERE id IN ({qmarks})",
        tuple(capture_ids),
    ).fetchall()
    return rows_to_dicts(rows)
