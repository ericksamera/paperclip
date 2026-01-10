from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from ..present import present_capture_detail
from ..repo import captures_repo


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    category: str = "success"  # success | warning | error
    changed_count: int = 0
    cleanup_paths: list[str] = field(default_factory=list)


def capture_detail_context(
    db,
    *,
    capture_id: str,
    artifacts_root: Path,
    allowed_artifacts: Iterable[str],
) -> dict | None:
    """
    Service wrapper for the capture detail page.

    - Fetches capture row
    - Builds the full template context via present_capture_detail(...)
    - Returns None if capture not found
    """
    row = captures_repo.get_capture(db, capture_id)
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

    return ActionResult(
        ok=True, message="Collections updated.", category="success", changed_count=1
    )


def delete_captures(
    db,
    *,
    capture_ids: Sequence[str],
    artifacts_root: Path,
    fts_enabled: bool,
) -> ActionResult:
    ids = [str(x).strip() for x in (capture_ids or []) if str(x or "").strip()]
    # De-dupe while preserving order
    seen: set[str] = set()
    out_ids: list[str] = []
    for cid in ids:
        if cid in seen:
            continue
        seen.add(cid)
        out_ids.append(cid)

    if not out_ids:
        return ActionResult(
            ok=False, message="No captures selected.", category="warning"
        )

    captures_repo.delete_captures(db, capture_ids=out_ids, fts_enabled=fts_enabled)

    cleanup = [os.fspath(artifacts_root / cid) for cid in out_ids]
    return ActionResult(
        ok=True,
        message=f"Deleted {len(out_ids)} capture(s).",
        category="success",
        changed_count=len(out_ids),
        cleanup_paths=cleanup,
    )


def bulk_add_to_collection(
    db,
    *,
    capture_ids: Sequence[str],
    collection_id: int | None,
    now: str,
) -> ActionResult:
    ids = [str(x).strip() for x in (capture_ids or []) if str(x or "").strip()]
    if not ids:
        return ActionResult(
            ok=False, message="No captures selected.", category="warning"
        )
    if not collection_id or int(collection_id) <= 0:
        return ActionResult(ok=False, message="Pick a collection.", category="warning")

    captures_repo.bulk_add_to_collection(
        db,
        capture_ids=list(ids),
        collection_id=int(collection_id),
        now=now,
    )

    return ActionResult(
        ok=True,
        message=f"Added {len(ids)} capture(s) to collection.",
        category="success",
        changed_count=len(ids),
    )


def bulk_remove_from_collection(
    db,
    *,
    capture_ids: Sequence[str],
    collection_id: int | None,
    now: str,
) -> ActionResult:
    ids = [str(x).strip() for x in (capture_ids or []) if str(x or "").strip()]
    if not ids:
        return ActionResult(
            ok=False, message="No captures selected.", category="warning"
        )
    if not collection_id or int(collection_id) <= 0:
        return ActionResult(ok=False, message="Pick a collection.", category="warning")

    captures_repo.bulk_remove_from_collection(
        db,
        capture_ids=list(ids),
        collection_id=int(collection_id),
        now=now,
    )

    return ActionResult(
        ok=True,
        message=f"Removed {len(ids)} capture(s) from collection.",
        category="success",
        changed_count=len(ids),
    )
