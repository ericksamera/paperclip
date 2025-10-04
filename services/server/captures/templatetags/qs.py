from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from django import template

register = template.Library()


@register.simple_tag
def qs_update(params: Mapping[str, Any], **updates: Any) -> str:
    params = dict(params)
    for k, v in updates.items():
        if v is None:
            params.pop(k, None)
        else:
            params[k] = v
    return urlencode(params, doseq=True)


@register.simple_tag
def qs_sort(
    params: Mapping[str, Any],
    key: str,
    current_sort: str | None,
    current_dir: str | None,
    default_dir: str = "asc",
) -> str:
    params = dict(params)
    if current_sort == key:
        # toggle
        params["sort"] = key
        params["dir"] = "desc" if (current_dir or default_dir) == "asc" else "asc"
    else:
        params["sort"] = key
        params["dir"] = default_dir
    params.pop("page", None)
    return urlencode(params, doseq=True)
