from __future__ import annotations
from bs4 import BeautifulSoup, Tag
from ..base import BaseParser, ReferenceObj, DOI_RE

class ScienceDirectParser(BaseParser):
    NAME = "ScienceDirect"
    DOMAINS = ("sciencedirect.com", "elsevier.com")

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        if cls.matches_domain(url):
            return True

        canon = soup.find(
            "link",
            rel=lambda value: value
            and ("canonical" in (value if isinstance(value, str) else " ".join(value)).lower()),
        )
        if canon and "sciencedirect.com" in (canon.get("href") or ""):
            return True

        publisher = soup.find("meta", attrs={"name": "citation_publisher"})
        if publisher and "Elsevier" in (publisher.get("content") or ""):
            return True

        site = soup.find("meta", attrs={"property": "og:site_name"})
        if site and "ScienceDirect" in (site.get("content") or ""):
            return True
        return False

    @classmethod
    def _harvest_references_generic(cls, soup: BeautifulSoup) -> list[ReferenceObj]:
        refs: list[ReferenceObj] = []
        selectors = [
            "section#references ol",
            "div#references ol",
            "ol.reference",
            "ol.bibliography",
            "div[class*='Reference'] ol",
        ]
        for sel in selectors:
            for lst in soup.select(sel):
                for li in lst.select(":scope > li"):
                    raw = cls._text(li)
                    if not raw:
                        continue
                    href = ""
                    anchor = li.select_one('a[href*="doi.org/10."]')
                    if anchor and anchor.get("href"):
                        href = anchor["href"]
                    match = DOI_RE.search(href) or DOI_RE.search(raw)
                    ref = ReferenceObj.from_raw_heuristic(raw, id=f"ref-{len(refs)+1}")
                    if match and not ref.doi:
                        ref.doi = match.group(0)
                    refs.append(ref)

        if refs:
            return refs

        return super()._harvest_references_generic(soup)

    @classmethod
    def _should_skip_abstract_candidate(cls, node: Tag) -> bool:
        if super()._should_skip_abstract_candidate(node):
            return True
        classes = {
            value.lower()
            for value in (node.get("class") or [])
            if isinstance(value, str)
        }
        skip_markers = {
            "graphical",
            "graphicalabstract",
            "graphical-abstract",
            "highlights",
        }
        if classes & skip_markers:
            return True
        heading = cls._leading_heading(node)
        if heading:
            heading_text = heading.get_text(" ", strip=True).lower()
            if heading_text.startswith("graphical abstract"):
                return True
            if heading_text.startswith("graphical summary"):
                return True
