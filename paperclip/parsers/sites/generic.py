from __future__ import annotations
from bs4 import BeautifulSoup
from ..base import BaseParser

class GenericParser(BaseParser):
    NAME = "Generic"
    DOMAINS = tuple()

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        return True

