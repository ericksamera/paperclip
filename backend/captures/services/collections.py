from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from io import BytesIO
from typing import Any, Iterable, Mapping

from captures.models import Capture, Collection
from captures.reduced_view import read_reduced_view
from captures.types import CSL
from captures.views.common import _author_list, _family_from_name, _journal_full


def _ascii_slug(s: str) -> str:
    """
    Fold accents → ASCII, keep [a-z0-9-], collapse dashes, lowercase.
    Mirrors captures.views.collections._ascii_slug.
    """
    s = (
        unicodedata.normalize("NFKD", (s or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    s = re.sub(r"-{2,}", "-", s)
    return s or "item"


def _slug_for_capture(c: Capture) -> str:
    """
    {year}_{first-author-family-name}_{journal-short-name}
    Fallbacks: year='na', author='anon', journal='journal'.

    Mirrors the slug logic in captures.views.collections so filenames stay stable. :contentReference[oaicite:0]{index=0}
    """
    meta: Mapping[str, Any] = c.meta or {}
    csl: CSL | Mapping[str, Any] = c.csl or {}
    year = (
        c.year or meta.get("year") or meta.get("publication_year") or ""
    ).strip() or "na"
    authors = _author_list(meta, csl)
    fam = _family_from_name(authors[0]) if authors else ""
    fam_slug = _ascii_slug(fam or "anon") or "anon"
    j_full = _journal_full(meta, csl)
    from paperclip.journals import (
        get_short_journal_name,
    )  # local import to avoid cycles

    j_short = get_short_journal_name(j_full, csl) or j_full or "journal"
    j_slug = _ascii_slug(j_short) or "journal"
    return f"{year}_{fam_slug}_{j_slug}"


def export_views_zip(captures: Iterable[Capture]) -> bytes:
    """
    Build a zip of reduced views for the given captures.

    Each entry is '<slug>__<id>.json' containing the reduced view JSON for that
    capture. If reduced view is missing, that capture is skipped.
    """
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in captures:
            view = read_reduced_view(str(c.id))
            if not view:
                continue
            slug = _slug_for_capture(c)
            arcname = f"{slug}__{c.id}.json"
            payload = json.dumps(view, ensure_ascii=False, indent=2)
            zf.writestr(arcname, payload)
    buf.seek(0)
    return buf.read()


def delete_collection(col: Collection, *, force: bool) -> tuple[bool, str | None]:
    """
    Core delete logic shared by views and commands.

    Returns (ok, error_message_or_none).
    - If not forced and collection has children/items → (False, msg).
    - If forced → clear items, reparent children to parent (if any), then delete.
    """
    has_children = col.children.exists()
    has_items = col.captures.exists()

    if (has_children or has_items) and not force:
        return False, "Collection is not empty. Re-run with force=1 to delete."

    if force:
        parent = col.parent
        if has_items:
            col.captures.clear()
        if has_children:
            for child in col.children.all():
                child.parent = parent
                child.save(update_fields=["parent"])

    col.delete()
    return True, None


def assign_captures(col: Collection, ids: Iterable[str], op: str = "add") -> None:
    """
    Add or remove captures from a collection.

    op: "add" (default) or "remove".
    """
    qs = Capture.objects.filter(id__in=list(ids))
    if op.lower() == "remove":
        col.captures.remove(*qs)
    else:
        col.captures.add(*qs)
