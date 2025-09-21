from __future__ import annotations
from bs4 import BeautifulSoup
from ..base import BaseParser, ParseResult

class GenericParser(BaseParser):
    NAME = "Generic"
    DOMAINS = tuple()

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        return True

    @classmethod
    def parse(cls, url: str, soup: BeautifulSoup) -> ParseResult:
        refs = cls._harvest_references_generic(soup)
        meta_updates = {}
        doi = cls.find_doi_in_meta(soup)
        if doi: meta_updates["doi"] = doi
        return ParseResult(meta_updates=meta_updates, references=refs, figures=[], tables=[])
