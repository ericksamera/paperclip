from __future__ import annotations

from typing import Any


def safe_int(val: Any) -> int | None:
    """
    Parse an int safely.
    Returns None on missing/invalid input.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None
