from __future__ import annotations
from bs4 import BeautifulSoup
from ..base import GeneralParser

class GenericParser(GeneralParser):
    NAME = "Generic"
    DOMAINS = tuple()

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        return True

