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

            if self.section_predicate(node):
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
                return

            for child in node.find_all(["section", "div"], recursive=False):
                consider(child)

        if body_root:
            for child in body_root.find_all(["section", "div"], recursive=False):
                consider(child)

        for selector in (
            "section[id], div[id]",
            "section.article-section, section.article-section__content, div.article-section__content",
        ):
            if sections:
                break
            for candidate in soup.select(selector):
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
        if node.name not in {"section", "div"}:
            return False
        classes = {
            value.lower()
            for value in (node.get("class") or [])
            if isinstance(value, str)
        }

        if any("abstract" in class_name for class_name in classes):
            return False

        data_section_type = node.get("data-section-type")
        if isinstance(data_section_type, str) and data_section_type.lower() in {
            "body",
            "full",
            "fulltext",
            "article-body",
        }:
            return True

        data_locator = node.get("data-test-locator") or node.get("data-testid")
        if isinstance(data_locator, str) and "article-section" in data_locator.lower():
            return True

        if not classes:
            content = node.find(
                class_=lambda name: isinstance(name, str)
                and name.lower().startswith("article-section__content")
            )
            if content:
                return True

        if any(
            class_name.startswith("article-section__content")
            or class_name.startswith("article-section__sub-content")
            or class_name.startswith("article-section__full")
            for class_name in classes
        ):
            return True

        if "article-section" in classes and node.find(
            class_=lambda name: isinstance(name, str)
            and name.lower().startswith("article-section__content")
        ):
            return True

        heading = node.find(
            lambda tag: isinstance(tag, Tag)
            and any(
                isinstance(value, str)
                and (
                    "article-section__title" in value.lower()
                    or "article-section__sub-title" in value.lower()
                    or "section__title" in value.lower()
                    or "section__subtitle" in value.lower()
                )
                for value in (tag.get("class") or [])
            )
        )
        if heading:
            text = heading.get_text(" ", strip=True).lower()
            if text and "abstract" in text:
                return False
            return True

        labelled = node.get("aria-labelledby")
        if isinstance(labelled, str) and labelled.strip():
            heading = node.find(id=labelled.strip())
            if isinstance(heading, Tag):
                text = heading.get_text(" ", strip=True).lower()
                if text and "abstract" not in text:
                    return True

        return False
