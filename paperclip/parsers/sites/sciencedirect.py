from __future__ import annotations
from bs4 import BeautifulSoup, Tag, NavigableString
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
            "div.abstract.author",
            "section.abstract",
            "section#abstract",
            "section#abstracts div.abstract",
            "div#abstract",
            "div.abstract",
        ]
        seen = set()
        for sel in selectors:
            for node in soup.select(sel):
                ident = id(node)
                if ident in seen:
                    continue
                seen.add(ident)
                text = cls._abstract_from_node(node)
                if text:
                    return text
        return ""

    @classmethod
    def _abstract_from_node(cls, node: Tag) -> str:
        if cls._should_skip_candidate(node):
            return ""
        text = node.get_text(" ", strip=True)
        if not text:
            return ""
        heading = cls._leading_heading(node)
        if heading:
            head_text = heading.get_text(" ", strip=True)
            if head_text:
                upper_text = text.lstrip()
                if upper_text.upper().startswith(head_text.upper()):
                    text = upper_text[len(head_text):].strip()
        text = " ".join(text.split())
        return text

    @staticmethod
    def _leading_heading(node: Tag) -> Tag | None:
        for child in node.children:
            if isinstance(child, NavigableString):
                if child.strip():
                    break
                continue
            if child.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                return child
            if child.get_text(" ", strip=True):
                break
        return None

    @classmethod
    def _should_skip_candidate(cls, node: Tag) -> bool:
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
        return False
