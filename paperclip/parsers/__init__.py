from __future__ import annotations
from bs4 import BeautifulSoup
from .registry import register, run_parser
from .base import ParseResult

# Import site adapters (registration happens on import)
from .sites.generic import GenericParser
from .sites.oup import OUPParser
from .sites.wiley import WileyParser
from .sites.sciencedirect import ScienceDirectParser

# Register in order of specificity (Generic last)
register(OUPParser)
register(WileyParser)
register(ScienceDirectParser)
register(GenericParser)

def parse_html(url: str, html: str) -> ParseResult:
    soup = BeautifulSoup(html or "", "html.parser")
    return run_parser(url, soup)


def parse_with_fallback(
    url: str,
    primary_html: str | None,
    fallback_html: str | None,
) -> ParseResult:
    """Parse the browser fragment but fall back to the full DOM when needed."""

    source_html = primary_html if primary_html is not None else fallback_html
    parsed = parse_html(url, source_html or "")

    if (
        primary_html
        and not parsed.references
        and fallback_html
        and fallback_html is not source_html
    ):
        fallback = parse_html(url, fallback_html)
        if fallback.references:
            return fallback

    return parsed
