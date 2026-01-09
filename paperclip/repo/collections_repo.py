from __future__ import annotations

from typing import Any

from ..db import rows_to_dicts


def list_collections_with_counts(db) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT c.id, c.name, COUNT(ci.capture_id) AS count
        FROM collections c
        LEFT JOIN collection_items ci ON ci.collection_id = c.id
        GROUP BY c.id
        ORDER BY c.name COLLATE NOCASE ASC
        """
    ).fetchall()
    return rows_to_dicts(rows)


def create_collection(db, *, name: str, created_at: str) -> None:
    db.execute(
        "INSERT INTO collections(name, created_at) VALUES(?, ?)",
        (name, created_at),
    )


def rename_collection(db, *, collection_id: int, name: str) -> None:
    db.execute("UPDATE collections SET name = ? WHERE id = ?", (name, collection_id))


def delete_collection(db, *, collection_id: int) -> None:
    db.execute("DELETE FROM collection_items WHERE collection_id = ?", (collection_id,))
    db.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
