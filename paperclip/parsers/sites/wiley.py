from __future__ import annotations
from urllib.parse import urlparse
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ..base import BaseParser, ReferenceObj, DOI_RE
from .sciencedirect.body import BodyExtractor
from .sciencedirect.citations import SentenceCitationAnnotator


class WileyBodyExtractor(BodyExtractor):
    def extract(self, soup: BeautifulSoup) -> list[dict[str, object]]:  # type: ignore[override]
        body_root = self._locate_body_root(soup)
        sections: list[Tag] = []
        seen: set[int] = set()

        def consider(node: Tag) -> None:
            if not isinstance(node, Tag):
                return
            if not self.section_predicate(node):
                return
            if any(
                isinstance(parent, Tag)
                and parent is not node
                and self.section_predicate(parent)
                for parent in node.parents
            ):
                return
            marker = id(node)
            if marker in seen:
                return
            seen.add(marker)
            sections.append(node)

        if body_root:
            for child in body_root.find_all("section", recursive=False):
                consider(child)

        if not sections:
            for candidate in soup.select("section[id]"):
                consider(candidate)

        if not sections:
            for candidate in soup.select("section.article-section, section.article-section__content"):
                consider(candidate)

        if not sections:
            return super().extract(soup)

        results: list[dict[str, object]] = []
        for idx, section in enumerate(sections, start=1):
            built = self._build_body_section(section, fallback_title=f"Section {idx}")
            if built:
                results.append(built)
        return results

    def _content_root(self, node: Tag) -> Tag:  # type: ignore[override]
        if node.name != "section":
            return node
        for child in node.find_all(True, recursive=False):
            if child.name != "div":
                continue
            classes = {
                value.lower()
                for value in (child.get("class") or [])
                if isinstance(value, str)
            }
            if any(class_name.startswith("article-section__content") for class_name in classes):
                return child
        return node

    def _locate_body_root(self, soup: BeautifulSoup) -> Tag | None:  # type: ignore[override]
        selectors = [
            "div.article__sections",
            "div.article__body",
            "section.article-body",
            "div#pb-page-content",
            "div#article-body",
            "div#main-content",
            "article.article",
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if isinstance(node, Tag):
                return node

        first_section = soup.select_one("section.article-section__content")
        if isinstance(first_section, Tag):
            parent = first_section.parent
            if isinstance(parent, Tag):
                return parent

        return super()._locate_body_root(soup)

class WileyParser(BaseParser):
    NAME = "Wiley"
    DOMAINS = ("onlinelibrary.wiley.com",)
    ABSTRACT_SELECTORS = BaseParser.ABSTRACT_SELECTORS + (
        "div.abstract-group div.article-section__content",
        "section.article-section__abstract div.article-section__content",
    )
    _body_extractor: ClassVar[BodyExtractor | None] = None

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        if cls.matches_domain(url):
            return True

        host = urlparse(url).netloc.lower()
        if "wiley" in host:
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

    @classmethod
    def _build_content_sections(cls, soup: BeautifulSoup) -> dict[str, object]:
        content = super()._build_content_sections(soup)
        body_sections = cls._extract_body_sections(soup)
        if body_sections:
            content["body"] = body_sections
        return content

    @classmethod
    def _extract_body_sections(cls, soup: BeautifulSoup) -> list[dict[str, object]]:
        extractor = cls._get_body_extractor()
        return extractor.extract(soup)

    @classmethod
    def _get_body_extractor(cls) -> BodyExtractor:
        if cls._body_extractor is None:
            cls._body_extractor = WileyBodyExtractor(
                citation_annotator=SentenceCitationAnnotator(),
                section_predicate=cls._is_wiley_section,
                heading_finder=BaseParser._leading_heading,
            )
        return cls._body_extractor

    @classmethod
    def _is_wiley_section(cls, node: Tag) -> bool:
        if node.name != "section":
            return False
        classes = {
            value.lower()
            for value in (node.get("class") or [])
            if isinstance(value, str)
        }
        if not classes:
            content = node.find(
                class_=lambda name: isinstance(name, str)
                and name.lower().startswith("article-section__content")
            )
            return bool(content)
        if "article-section__content" in classes:
            return True
        if "article-section" in classes and node.find(
            class_=lambda name: isinstance(name, str)
            and name.lower().startswith("article-section__content")
        ):
            return True
        return any(
            class_name.startswith("article-section__content")
            for class_name in classes
        )
