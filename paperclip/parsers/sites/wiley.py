from __future__ import annotations
from bs4 import BeautifulSoup
from ..base import BaseParser, ReferenceObj, DOI_RE

class WileyParser(BaseParser):
    NAME = "Wiley"
    DOMAINS = ("onlinelibrary.wiley.com",)
    ABSTRACT_SELECTORS = BaseParser.ABSTRACT_SELECTORS + (
        "div.abstract-group div.article-section__content",
        "section.article-section__abstract div.article-section__content",
    )

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        if cls.matches_domain(url):
            return True

        canon = soup.find(
            "link",
            rel=lambda value: value
            and ("canonical" in (value if isinstance(value, str) else " ".join(value)).lower()),
        )
        if canon and "onlinelibrary.wiley.com" in (canon.get("href") or ""):
            return True

        publisher = soup.find("meta", attrs={"name": "citation_publisher"})
        if publisher and "Wiley" in (publisher.get("content") or ""):
            return True

        site = soup.find("meta", attrs={"property": "og:site_name"})
        if site and "Wiley" in (site.get("content") or ""):
            return True
        return False

    @classmethod
    def _harvest_references_generic(cls, soup: BeautifulSoup) -> list[ReferenceObj]:
        refs: list[ReferenceObj] = []
        selectors = [
            "section.article-section__references ol",
            "section#references ol",
            "ol.cited-by-list",
            "ol.ref-list",
            "div.article-section__references ol",
        ]
        for sel in selectors:
            for lst in soup.select(sel):
                for li in lst.select(":scope > li"):
                    raw = cls._text(li)
                    if not raw:
                        continue
                    match = DOI_RE.search(raw) or DOI_RE.search(li.get("data-doi") or "")
                    ref = ReferenceObj.from_raw_heuristic(raw, id=f"ref-{len(refs)+1}")
                    if match and not ref.doi:
                        ref.doi = match.group(0)
                    refs.append(ref)

        if refs:
            return refs

        return super()._harvest_references_generic(soup)
