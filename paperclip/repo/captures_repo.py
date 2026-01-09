from __future__ import annotations

from typing import Any

from ..db import rows_to_dicts


def get_capture(db, capture_id: str) -> dict[str, Any] | None:
    row = db.execute("SELECT * FROM captures WHERE id = ?", (capture_id,)).fetchone()
    return dict(row) if row else None


def list_collections_for_capture(db, capture_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT c.id, c.name,
               CASE WHEN ci.capture_id IS NULL THEN 0 ELSE 1 END AS has_it
        FROM collections c
        LEFT JOIN collection_items ci
          ON ci.collection_id = c.id AND ci.capture_id = ?
        ORDER BY c.name COLLATE NOCASE ASC
        """,
        (capture_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def _current_collection_ids(db, capture_id: str) -> set[int]:
    rows = db.execute(
        "SELECT collection_id FROM collection_items WHERE capture_id = ?",
        (capture_id,),
    ).fetchall()
    out: set[int] = set()
    for r in rows:
        try:
            out.add(int(r["collection_id"]))
        except Exception:
            continue
    return out


def set_capture_collections(
    db,
    *,
    capture_id: str,
    selected_ids: set[int],
    now: str,
) -> None:
    """
    Replace the set of collections for a capture.
    Does NOT commit.
    """
    cur_ids = _current_collection_ids(db, capture_id)

    to_add = sorted(selected_ids - cur_ids)
    to_remove = sorted(cur_ids - selected_ids)

    for cid in to_add:
        db.execute(
            "INSERT OR IGNORE INTO collection_items(collection_id, capture_id, added_at) VALUES(?, ?, ?)",
            (cid, capture_id, now),
        )
    for cid in to_remove:
        db.execute(
            "DELETE FROM collection_items WHERE collection_id = ? AND capture_id = ?",
            (cid, capture_id),
        )

    db.execute(
        "UPDATE captures SET updated_at = ? WHERE id = ?",
        (now, capture_id),
    )


def delete_captures(db, *, capture_ids: list[str], fts_enabled: bool) -> None:
    """
    Delete captures and related rows. Does NOT commit.
    We explicitly delete from capture_fts because it's a virtual table.
    """
    for cid in capture_ids:
        db.execute("DELETE FROM collection_items WHERE capture_id = ?", (cid,))
        db.execute("DELETE FROM capture_text WHERE capture_id = ?", (cid,))
        if fts_enabled:
            db.execute("DELETE FROM capture_fts WHERE capture_id = ?", (cid,))
        db.execute("DELETE FROM captures WHERE id = ?", (cid,))


def bulk_add_to_collection(
    db,
    *,
    capture_ids: list[str],
    collection_id: int,
    now: str,
) -> None:
    """
    Add each capture to a collection and bump updated_at. Does NOT commit.
    """
    for cid in capture_ids:
        db.execute(
            "INSERT OR IGNORE INTO collection_items(collection_id, capture_id, added_at) VALUES(?, ?, ?)",
            (collection_id, cid, now),
        )
        db.execute("UPDATE captures SET updated_at = ? WHERE id = ?", (now, cid))


def bulk_remove_from_collection(
    db,
    *,
    capture_ids: list[str],
    collection_id: int,
    now: str,
) -> None:
    """
    Remove each capture from a collection and bump updated_at. Does NOT commit.
    """
    for cid in capture_ids:
        db.execute(
            "DELETE FROM collection_items WHERE collection_id = ? AND capture_id = ?",
            (collection_id, cid),
        )
        db.execute("UPDATE captures SET updated_at = ? WHERE id = ?", (now, cid))
