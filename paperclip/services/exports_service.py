from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ..export import captures_to_bibtex, captures_to_ris
from ..parseutil import safe_int
from ..repo import exports_repo


def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:80] if s else "export"


@dataclass(frozen=True)
class ExportContext:
    captures: list[dict]
    capture_id: str | None
    col_id: int | None
    col_name: str | None


def select_export_context(
    db,
    *,
    capture_id: str | None,
    col: str | None,
) -> ExportContext:
    """
    Service-level decision logic:
      - if capture_id provided => export that one capture (if it exists; otherwise empty)
      - else if collection id provided => export that collection (and attach col_name)
      - else => export all
    """
    cap_id = (capture_id or "").strip() or None
    col_raw = (col or "").strip() or None

    if cap_id:
        cap = exports_repo.get_capture_by_id(db, capture_id=cap_id)
        caps = [cap] if cap else []
        return ExportContext(
            captures=caps, capture_id=cap_id, col_id=None, col_name=None
        )

    col_id = safe_int(col_raw)
    if col_id and col_id > 0:
        caps = exports_repo.list_captures_in_collection(db, collection_id=int(col_id))
        col_name = exports_repo.get_collection_name(db, collection_id=int(col_id))
        return ExportContext(
            captures=caps, capture_id=None, col_id=int(col_id), col_name=col_name
        )

    caps = exports_repo.list_all_captures(db)
    return ExportContext(captures=caps, capture_id=None, col_id=None, col_name=None)


def export_filename(
    *,
    ext: str,
    capture_id: str | None,
    col_id: int | None,
    col_name: str | None,
    selected: bool,
) -> str:
    base = "paperclip"

    if capture_id:
        base = f"{base}_{_slug(capture_id)[:12]}"
    elif col_name:
        base = f"{base}_{_slug(col_name)}"
    elif col_id:
        base = f"{base}_col{col_id}"

    if selected:
        base = f"{base}_selected"

    return f"{base}.{ext}"


ExportKind = Literal["bibtex", "ris"]


def render_export(
    *,
    kind: ExportKind,
    captures: list[dict],
) -> tuple[str, str]:
    """
    Returns (body, mimetype).
    """
    if kind == "bibtex":
        return captures_to_bibtex(captures), "application/x-bibtex"
    if kind == "ris":
        return captures_to_ris(captures), "application/x-research-info-systems"
    raise ValueError(f"Unknown export kind: {kind}")


def select_captures_by_ids(db, *, capture_ids: list[str]) -> list[dict]:
    return exports_repo.select_captures_by_ids(db, capture_ids=capture_ids)
