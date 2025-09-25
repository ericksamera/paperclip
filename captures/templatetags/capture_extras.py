# captures/templatetags/capture_extras.py
from __future__ import annotations
from urllib.parse import urlparse
from django import template

register = template.Library()

def _label_from_host(host: str) -> str:
    h = (host or "").lower().lstrip("www.")
    # Friendly short labels for common hosts
    if h.endswith("pmc.ncbi.nlm.nih.gov"): return "PMC"
    if h.endswith("biomedcentral.com"):     return "BMC"
    if h.endswith("wiley.com"):             return "Wiley"
    if h.endswith("nature.com"):            return "Nature"
    if h.endswith("springer.com") or h.endswith("springeropen.com"): return "Springer"
    if h.endswith("sciencedirect.com"):     return "ScienceDirect"
    if h.endswith("plos.org"):              return "PLOS"
    if h.endswith("nih.gov"):               return "NIH"
    # fallback: registrable-ish part
    parts = h.split(".")
    if len(parts) >= 2:
        return parts[-2].capitalize()
    return host or "Site"

@register.filter
def site_label(url: str) -> str:
    """Return a short, human label for a capture url ('PMC', 'BMC', etc.)."""
    if not url:
        return ""
    host = urlparse(url).netloc
    return _label_from_host(host)

@register.filter
def doi_url(doi: str | None) -> str:
    """Build a https://doi.org/<doi> url if it looks like a DOI."""
    d = (doi or "").strip()
    if not d:
        return ""
    return f"https://doi.org/{d}" if d.startswith("10.") else d

@register.filter
def dash(value):
    """Render a nice em dash when value is falsy/empty."""
    return value if value not in (None, "", [], {}) else "—"
