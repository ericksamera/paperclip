from __future__ import annotations

from typing import Any

from flask import redirect, request, url_for

from .parseutil import safe_int


def parse_page_size(val: Any, default: int) -> int:
    n = safe_int(val)
    if n is None or n <= 0:
        return default
    return min(500, n)


def redirect_next(default_endpoint: str = "library"):
    nxt = (request.form.get("next") or "").strip()
    if nxt:
        return redirect(nxt)
    return redirect(request.referrer or url_for(default_endpoint))
