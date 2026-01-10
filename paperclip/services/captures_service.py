from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from ..present import present_capture_detail
from ..repo import captures_repo
from .types import ActionResult


def capture_detail_context(
    db,
    *,
    capture_id: str,
    artifacts_root: Path,
    allowed_artifacts: Iterable[str],
) -> dict | None:
    row = captures_repo.get_capture(db, capture_id=capture_id)
    if not row:
        return None

    return present_capture_detail(
        db=db,
        capture_row=row,
        capture_id=capture_id,
        artifacts_root=artifacts_root,
        allowed_artifacts=allowed_artifacts,
    )


def set_capture_collections(
    db,
    *,
    capture_id: str,
    selected_ids: set[int],
    now: str,
) -> ActionResult:
    row = db.execute("SELECT id FROM captures WHERE id = ?", (capture_id,)).fetchone()
    if not row:
        return ActionResult(ok=False, message="Capture not found.", category="error")

    captures_repo.set_capture_collections(
        db,
        capture_id=capture_id,
        selected_ids=selected_ids,
        now=now,
    )
    return ActionResult(ok=True, message="Saved.", category="success")


def delete_captures(
    db,
    *,
    capture_ids: Sequence[str],
    artifacts_root: Path,
    fts_enabled: bool,
) -> ActionResult:
    ids = [c for c in (capture_ids or []) if str(c or "").strip()]
    if not ids:
        return ActionResult(
            ok=False, message="No captures selected.", category="warning"
        )

    existing = captures_repo.list_existing_capture_ids(db, capture_ids=list(ids))
    if not existing:
        return ActionResult(
            ok=False, message="No matching captures found.", category="warning"
        )

    deleted = captures_repo.delete_captures(
        db, capture_ids=existing, fts_enabled=fts_enabled
    )

    cleanup_paths = [str(artifacts_root / cid) for cid in existing]

    return ActionResult(
        ok=True,
        message=f"Deleted {deleted} capture(s).",
        category="success",
        changed_count=deleted,
        cleanup_paths=cleanup_paths,
    )


def bulk_add_to_collection(
    db,
    *,
    capture_ids: Sequence[str],
    collection_id: int | None,
    now: str,
) -> ActionResult:
    ids = [c for c in (capture_ids or []) if str(c or "").strip()]
    if not ids:
        return ActionResult(
            ok=False, message="No captures selected.", category="warning"
        )

    if not collection_id:
        return ActionResult(
            ok=False, message="Choose a collection.", category="warning"
        )

    existing = captures_repo.list_existing_capture_ids(db, capture_ids=list(ids))
    if not existing:
        return ActionResult(
            ok=False, message="No matching captures found.", category="warning"
        )

    changed = captures_repo.bulk_add_to_collection(
        db,
        capture_ids=existing,
        collection_id=int(collection_id),
        now=now,
    )

    return ActionResult(
        ok=True,
        message=f"Added {changed} capture(s) to collection.",
        category="success",
        changed_count=changed,
    )


def bulk_remove_from_collection(
    db,
    *,
    capture_ids: Sequence[str],
    collection_id: int | None,
    now: str,
) -> ActionResult:
    ids = [c for c in (capture_ids or []) if str(c or "").strip()]
    if not ids:
        return ActionResult(
            ok=False, message="No captures selected.", category="warning"
        )

    if not collection_id:
        return ActionResult(
            ok=False, message="Choose a collection.", category="warning"
        )

    existing = captures_repo.list_existing_capture_ids(db, capture_ids=list(ids))
    if not existing:
        return ActionResult(
            ok=False, message="No matching captures found.", category="warning"
        )

    changed = captures_repo.bulk_remove_from_collection(
        db,
        capture_ids=existing,
        collection_id=int(collection_id),
        now=now,
    )

    return ActionResult(
        ok=True,
        message=f"Removed {changed} capture(s) from collection.",
        category="success",
        changed_count=changed,
    )
