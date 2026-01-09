from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .base import ParseResult
from .elsevier import parse_elsevier
from .generic import parse_generic
from .pmc import parse_pmc


def _site_kind(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if "ncbi.nlm.nih.gov" in host and "/pmc/" in (urlparse(url).path or "").lower():
        return "pmc"
    if "sciencedirect.com" in host or "elsevier.com" in host:
        return "elsevier"
    return "generic"


def parse_article(*, url: str, dom_html: str, head_meta: dict[str, Any]) -> ParseResult:
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
