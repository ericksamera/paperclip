from __future__ import annotations
from django import template
from urllib.parse import urlencode

register = template.Library()

@register.simple_tag
def qs_update(params, **updates):
    params = dict(params)
    for k, v in updates.items():
        if v is None:
            params.pop(k, None)
        else:
            params[k] = v
    return urlencode(params, doseq=True)

@register.simple_tag
def qs_sort(params, key, current_sort, current_dir, default_dir="asc"):
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
