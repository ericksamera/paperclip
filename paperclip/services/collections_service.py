from __future__ import annotations

from typing import Any

import sqlite3

from ..repo import collections_repo
from .types import ActionResult


def list_collections_with_counts(db) -> list[dict[str, Any]]:
    return collections_repo.list_collections_with_counts(db)


def create_collection(db, *, name: str, created_at: str) -> ActionResult:
    n = (name or "").strip()
    if not n:
        return ActionResult(ok=False, message="Name required.", category="warning")

    try:
        collections_repo.create_collection(db, name=n, created_at=created_at)
    except sqlite3.IntegrityError:
        return ActionResult(
            ok=False, message="Collection already exists.", category="warning"
        )

    return ActionResult(ok=True, message="Collection created.", category="success")


def rename_collection(db, *, collection_id: int, name: str) -> ActionResult:
    n = (name or "").strip()
    if not n:
        return ActionResult(ok=False, message="Name required.", category="warning")

    try:
        changed = collections_repo.rename_collection(
            db, collection_id=collection_id, name=n
        )
    except sqlite3.IntegrityError:
        # tests expect this exact message
        return ActionResult(
            ok=False, message="Collection name already exists.", category="warning"
        )

    if not changed:
        return ActionResult(ok=False, message="Collection not found.", category="error")

    return ActionResult(
        ok=True, message="Renamed.", category="success", changed_count=changed
    )


def delete_collection(db, *, collection_id: int) -> ActionResult:
    changed = collections_repo.delete_collection(db, collection_id=collection_id)
    if not changed:
        return ActionResult(ok=False, message="Collection not found.", category="error")

    return ActionResult(
        ok=True, message="Deleted.", category="success", changed_count=changed
    )
