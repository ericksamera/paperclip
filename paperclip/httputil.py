from __future__ import annotations

from typing import Any

from flask import redirect, request, url_for


def parse_int(val: Any, default: int) -> int:
    try:
        return int(val)
    except Exception:
        return default


def parse_page_size(val: Any, default: int) -> int:
    n = parse_int(val, default)
    if n <= 0:
        return default
    return min(500, n)


def redirect_next(default_endpoint: str = "library"):
    nxt = (request.form.get("next") or "").strip()
    if nxt:
        return redirect(nxt)
    return redirect(request.referrer or url_for(default_endpoint))
