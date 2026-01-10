from __future__ import annotations


def find_capture_by_doi(db, *, doi: str):
    if not doi:
        return None
    return db.execute(
        "SELECT id, created_at FROM captures WHERE doi = ? AND doi <> '' LIMIT 1",
        (doi,),
    ).fetchone()


def find_capture_by_url_hash(db, *, url_hash: str):
    if not url_hash:
        return None
    return db.execute(
        "SELECT id, created_at FROM captures WHERE url_hash = ? LIMIT 1",
        (url_hash,),
    ).fetchone()


def _rowid_for_id(db, capture_id: str) -> int | None:
    try:
        row = db.execute(
            "SELECT rowid AS rid FROM captures WHERE id = ? LIMIT 1", (capture_id,)
        ).fetchone()
        if not row:
            return None
        rid = row["rid"]
        return int(rid) if rid is not None else None
    except Exception:
        return None


def merge_duplicate_capture(
    db,
    *,
    keep_id: str,
    drop_id: str,
    fts_enabled: bool,
) -> None:
    """
    Move collection membership from drop_id -> keep_id, delete drop capture row,
    and delete FTS row if enabled. Does NOT commit.
    """
    if not keep_id or not drop_id or keep_id == drop_id:
        return

    rows = db.execute(
        "SELECT collection_id, added_at FROM collection_items WHERE capture_id = ?",
        (drop_id,),
    ).fetchall()

    for r in rows:
        db.execute(
            "INSERT OR IGNORE INTO collection_items (collection_id, capture_id, added_at) VALUES (?, ?, ?)",
            (r["collection_id"], keep_id, r["added_at"]),
        )

    if fts_enabled:
        try:
            rid = _rowid_for_id(db, drop_id)
            if rid is not None:
                db.execute("DELETE FROM capture_fts WHERE rowid = ?", (rid,))
        except Exception:
            pass

    db.execute("DELETE FROM captures WHERE id = ?", (drop_id,))
