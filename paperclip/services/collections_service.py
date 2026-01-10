from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sqlite3

from ..repo import collections_repo


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    category: str = "success"  # success | warning | error


def list_collections_with_counts(db) -> list[dict[str, Any]]:
    return collections_repo.list_collections_with_counts(db)


def create_collection(db, *, name: str, created_at: str) -> ActionResult:
    n = (name or "").strip()
    if not n:
        return ActionResult(ok=False, message="Name required.", category="warning")

    try:
        collections_repo.create_collection(db, name=n, created_at=created_at)
    except sqlite3.IntegrityError:
        # UNIQUE(name)
        return ActionResult(
            ok=False, message="Collection already exists.", category="warning"
        )

    return ActionResult(ok=True, message="Collection created.", category="success")


def rename_collection(db, *, collection_id: int, name: str) -> ActionResult:
    n = (name or "").strip()
    if not n:
        return ActionResult(ok=False, message="Name required.", category="warning")

    try:
        collections_repo.rename_collection(db, collection_id=collection_id, name=n)
    except sqlite3.IntegrityError:
        return ActionResult(
            ok=False, message="Collection name already exists.", category="warning"
        )

    return ActionResult(ok=True, message="Collection renamed.", category="success")


def delete_collection(db, *, collection_id: int) -> ActionResult:
    collections_repo.delete_collection(db, collection_id=collection_id)
    return ActionResult(ok=True, message="Collection deleted.", category="success")
