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
