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
        abstract = cls._extract_abstract(soup)
        if abstract:
            meta_updates["abstract"] = abstract
        return ParseResult(meta_updates=meta_updates, references=refs, figures=[], tables=[])

    @classmethod
    def _extract_abstract(cls, soup: BeautifulSoup) -> str:
        selectors = [
            "div.abstract",
            "section.abstract",
            "section#abstract",
            "div#abstract",
            "section#abstracts div.abstract",
        ]
        for sel in selectors:
            node = soup.select_one(sel)
            if not node:
                continue
            text = node.get_text(" ", strip=True)
            if not text:
                continue
            heading = node.find(["h1", "h2", "h3", "h4", "h5", "h6"])
            if heading:
                head_text = heading.get_text(" ", strip=True)
                if head_text:
                    upper_text = text.lstrip()
                    if upper_text.upper().startswith(head_text.upper()):
                        text = upper_text[len(head_text):].strip()
            if text:
                return text
        return ""
