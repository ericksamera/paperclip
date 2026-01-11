from __future__ import annotations

from typing import Any


def as_str(v: Any) -> str:
    """
    Best-effort string coercion.

    - None -> ""
    - str -> unchanged
    - list/tuple -> joined with "; " (skipping empties)
    - everything else -> str(v)
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        parts: list[str] = []
        for x in v:
            s = as_str(x)
            if s:
                parts.append(s)
        return "; ".join(parts)
    return str(v)
