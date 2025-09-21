from __future__ import annotations
from bs4 import BeautifulSoup
from ..base import BaseParser, ParseResult, ReferenceObj, DOI_RE

class ScienceDirectParser(BaseParser):
    NAME = "ScienceDirect"
    DOMAINS = ("sciencedirect.com", "elsevier.com")

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        if cls.matches_domain(url): return True
        canon = soup.find("link", rel=lambda v: v and ("canonical" in (v if isinstance(v, str) else " ".join(v)).lower()))
        if canon and "sciencedirect.com" in (canon.get("href") or ""): return True
        pub = soup.find("meta", attrs={"name": "citation_publisher"})
        if pub and "Elsevier" in (pub.get("content") or ""): return True
        site = soup.find("meta", attrs={"property": "og:site_name"})
        if site and "ScienceDirect" in (site.get("content") or ""): return True
        return False

    @classmethod
    def parse(cls, url: str, soup: BeautifulSoup) -> ParseResult:
        refs = []
        selectors = [
            "section#references ol",
            "div#references ol",
            "ol.reference",
            "ol.bibliography",
            "div[class*='Reference'] ol"
        ]
        for sel in selectors:
            for lst in soup.select(sel):
                for li in lst.select(":scope > li"):
                    raw = cls._text(li)
                    if not raw: continue
                    href = ""
                    a = li.select_one('a[href*="doi.org/10."]')
                    if a and a.get("href"): href = a["href"]
                    m = DOI_RE.search(href) or DOI_RE.search(raw)
                    ref = ReferenceObj.from_raw_heuristic(raw, id=f"ref-{len(refs)+1}")
                    if m and not ref.doi:
                        ref.doi = m.group(0)
                    refs.append(ref)

        if not refs:
            refs = cls._harvest_references_generic(soup)

        meta_updates = {}
        doi = cls.find_doi_in_meta(soup)
        if doi: meta_updates["doi"] = doi
        return ParseResult(meta_updates=meta_updates, references=refs, figures=[], tables=[])
