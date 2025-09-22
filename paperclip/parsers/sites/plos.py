from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup, Tag

from ..base import GeneralParser


class PLOSParser(GeneralParser):
    """Parser for PLOS journal articles."""

    NAME = "PLOS"
    DOMAINS = ("journals.plos.org",)

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        if cls.matches_domain(url):
            return True

        canonical = soup.find(
            "link",
            rel=lambda value: value
            and "canonical" in (value if isinstance(value, str) else " ".join(value)).lower(),
        )
        if canonical and "journals.plos.org" in (canonical.get("href") or ""):
            return True

        return False

    @classmethod
    def _extract_body_sections(cls, soup: BeautifulSoup) -> list[dict[str, Any]]:
        converted: list[Tag] = []
        for node in soup.select("div.section.toc-section"):
            if not isinstance(node, Tag):
                continue
            converted.append(node)
            node.name = "section"

        try:
            return super()._extract_body_sections(soup)
        finally:
            for node in converted:
                node.name = "div"

