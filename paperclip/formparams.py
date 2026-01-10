from __future__ import annotations

from typing import Any, Mapping

from .parseutil import safe_int


def get_next_arg(form: Mapping[str, Any]) -> str:
    return (str(form.get("next") or "")).strip()


def get_capture_ids(form: Mapping[str, Any]) -> list[str]:
    """
    Accepts either:
      - Werkzeug MultiDict with getlist()
      - plain dict with "capture_ids" as a str or list[str]
    Returns a de-duped, trimmed list, preserving order.
    """
    raw: list[Any]
    if hasattr(form, "getlist"):
        raw = list(form.getlist("capture_ids"))  # type: ignore[attr-defined]
    else:
        v = form.get("capture_ids")
        if v is None:
            raw = []
        elif isinstance(v, list):
            raw = v
        else:
            raw = [v]

    out: list[str] = []
    seen: set[str] = set()
    for x in raw:
        s = str(x or "").strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def get_collection_id(form: Mapping[str, Any]) -> int | None:
    v = safe_int(form.get("collection_id"))
    if v is None or v <= 0:
        return None
    return int(v)


def get_collection_ids(
    form: Mapping[str, Any], *, field: str = "collection_ids"
) -> set[int]:
    """
    For capture detail page: checkbox list like name="collection_ids".
    Returns a set[int] of valid ids.
    """
    if hasattr(form, "getlist"):
        raw = list(form.getlist(field))  # type: ignore[attr-defined]
    else:
        v = form.get(field)
        if v is None:
            raw = []
        elif isinstance(v, list):
            raw = v
        else:
            raw = [v]

    out: set[int] = set()
    for x in raw:
        i = safe_int(x)
        if i and i > 0:
            out.add(int(i))
    return out
