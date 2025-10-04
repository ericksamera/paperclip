from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def doi_url(doi: str | None) -> str | None:
    if not doi:
        return None
    if doi.startswith("http://") or doi.startswith("https://"):
        return doi
    return f"https://doi.org/{doi}"
