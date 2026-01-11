from __future__ import annotations

from urllib.parse import urlparse

from .base import ParseResult
from .generic import parse_generic
from .oup import parse_oup
from .pmc import parse_pmc
from .wiley import parse_wiley
from .sciencedirect import parse_sciencedirect


def _site_kind(url: str) -> str:
    u = urlparse(url)
    host = (u.netloc or "").lower()
    path = (u.path or "").lower()

    # PMC variants
    if (
        host.endswith("pmc.ncbi.nlm.nih.gov")
        or (("ncbi.nlm.nih.gov" in host) and ("/pmc/" in path))
        or ("/articles/pmc" in path)
    ):
        return "pmc"

    # OUP / Oxford Academic (handle institutional proxy hostnames too)
    if (
        ("oup.com" in host)
        or ("academic-oup-com" in host)
        or ("journals-oup-com" in host)
    ):
        return "oup"

    # Wiley Online Library (handle institutional proxy hostnames too)
    if (
        ("onlinelibrary.wiley.com" in host)
        or ("onlinelibrary-wiley-com" in host)
        or ("wiley.com" in host)
    ):
        return "wiley"

    # ScienceDirect / Elsevier (handle institutional proxy hostnames too)
    if (
        ("sciencedirect.com" in host)
        or ("sciencedirect-com" in host)  # common EZProxy rewrite
        or ("elsevier.com" in host)
        or ("elsevier-com" in host)  # common EZProxy rewrite
    ):
        return "sciencedirect"

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

    if kind == "oup":
        r = parse_oup(url=url, dom_html=dom_html, head_meta=head_meta)
        if r.ok and (r.article_html or r.article_text):
            return r

    if kind == "wiley":
        r = parse_wiley(url=url, dom_html=dom_html, head_meta=head_meta)
        if r.ok and (r.article_html or r.article_text):
            return r

    if kind == "sciencedirect":
        r = parse_sciencedirect(url=url, dom_html=dom_html, head_meta=head_meta)
        if r.ok and (r.article_html or r.article_text):
            return r

    return parse_generic(url=url, dom_html=dom_html, head_meta=head_meta)
