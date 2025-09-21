from __future__ import annotations
from typing import List, Type, Optional
from bs4 import BeautifulSoup
from .base import BaseParser, ParseResult

_REGISTRY: List[Type[BaseParser]] = []

def register(parser_cls: Type[BaseParser]) -> Type[BaseParser]:
    _REGISTRY.append(parser_cls)
    return parser_cls

def pick_parser(url: str, soup: BeautifulSoup) -> Type[BaseParser]:
    # Prefer explicit detects; fall back to first domain match; else Generic
    matches = []
    for cls in _REGISTRY:
        if cls.detect(url, soup):
            matches.append(cls)
    # If nothing detected, return Generic (which should always be registered last)
    return matches[0] if matches else _REGISTRY[-1]

def run_parser(url: str, soup: BeautifulSoup) -> ParseResult:
    parser_cls = pick_parser(url, soup)
    return parser_cls.parse(url, soup)
