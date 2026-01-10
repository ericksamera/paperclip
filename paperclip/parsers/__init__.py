from __future__ import annotations

from urllib.parse import urlparse

from .base import ParseResult
from .elsevier import parse_elsevier
from .generic import parse_generic
from .pmc import parse_pmc


def _site_kind(url: str) -> str:
    u = urlparse(url)
    host = (u.netloc or "").lower()
    path = (u.path or "").lower()

    # PMC variants:
    # - https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/
    # - https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567/
    # - (rare) other NCBI mirrors that still include /pmc/ or /articles/PMC...
    if (
        host.endswith("pmc.ncbi.nlm.nih.gov")
        or (("ncbi.nlm.nih.gov" in host) and ("/pmc/" in path))
        or ("/articles/pmc" in path)
    ):
        return "pmc"

    if "sciencedirect.com" in host or "elsevier.com" in host:
        return "elsevier"

    return "generic"


def parse_article(
    *, url: str, dom_html: str, head_meta: dict[str, object]
) -> ParseResult:
    """
    Site-aware parser dispatcher.
    Always returns a ParseResult. Prefer site-specific; fall back to generic.
    """
    kind = _site_kind(url)

    if kind == "pmc":
        r = parse_pmc(url=url, dom_html=dom_html, head_meta=head_meta)
        if r.ok and (r.article_html or r.article_text):
            return r

    if kind == "elsevier":
        r = parse_elsevier(url=url, dom_html=dom_html, head_meta=head_meta)
        if r.ok and (r.article_html or r.article_text):
            return r

    return parse_generic(url=url, dom_html=dom_html, head_meta=head_meta)
