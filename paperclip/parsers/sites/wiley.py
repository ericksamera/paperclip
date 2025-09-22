from __future__ import annotations
from urllib.parse import urlparse
from typing import TYPE_CHECKING, Any, ClassVar

from bs4 import BeautifulSoup, NavigableString, Tag

from ..base import BaseParser, ReferenceObj, DOI_RE
from .sciencedirect.body import BodyExtractor

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from .sciencedirect.citations import SentenceCitationAnnotator


class WileyBodyExtractor(BodyExtractor):
    _SECTION_TAGS: ClassVar[tuple[str, ...]] = ("section", "div")

    def extract(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        body_root = self._locate_body_root(soup)
        sections = self._collect_top_level_sections(soup, body_root)

        if not sections:
            return super().extract(soup)

        results: list[dict[str, Any]] = []
        for index, section in enumerate(sections, start=1):
            built = self._build_body_section(section, fallback_title=f"Section {index}")
            if built:
                results.append(built)
        return results

    def _collect_top_level_sections(
        self, soup: BeautifulSoup, body_root: Tag | None
    ) -> list[Tag]:
        """Collect Wiley body sections in document order.

        The DOM on Wiley frequently nests structural wrappers around the real
        section content.  Rather than chasing parents and children recursively,
        gather every matching node once and then retain the highest level nodes
        that contain actual content.
        """

        candidates: list[Tag] = []
        seen_nodes: set[int] = set()

        def queue_nodes(root: Tag | BeautifulSoup) -> None:
            if not isinstance(root, Tag):
                return
            if self.section_predicate(root):
                marker = id(root)
                if marker not in seen_nodes:
                    seen_nodes.add(marker)
                    candidates.append(root)

            for node in root.find_all(self._SECTION_TAGS):
                if not isinstance(node, Tag):
                    continue
                marker = id(node)
                if marker in seen_nodes:
                    continue
                if not self.section_predicate(node):
                    continue
                seen_nodes.add(marker)
                candidates.append(node)

        if body_root:
            queue_nodes(body_root)

        if not candidates:
            for selector in (
                "section[id]",
                "div[id]",
                "section.article-section",
                "div.article-section",
                "div.article-section__content",
                "section.article-section__content",
            ):
                for candidate in soup.select(selector):
                    if isinstance(candidate, Tag):
                        queue_nodes(candidate)
                if candidates:
                    break

        if not candidates:
            queue_nodes(soup)

        if not candidates:
            return []

        top_level: list[Tag] = []
        skipped_descendants: set[int] = set()

        for node in candidates:
            marker = id(node)
            if marker in skipped_descendants:
                continue
            if self._has_section_ancestor(node):
                continue
            if not self._has_direct_content(node) and self._has_section_descendant(node):
                continue
            top_level.append(node)
            for descendant in node.find_all(self._SECTION_TAGS):
                if isinstance(descendant, Tag):
                    skipped_descendants.add(id(descendant))

        return top_level

    def _has_section_ancestor(self, node: Tag) -> bool:
        for parent in node.parents:
            if isinstance(parent, Tag) and self.section_predicate(parent):
                return True
        return False

    def _has_section_descendant(self, node: Tag) -> bool:
        for descendant in node.find_all(self._SECTION_TAGS):
            if descendant is node:
                continue
            if isinstance(descendant, Tag) and self.section_predicate(descendant):
                return True
        return False

    def _has_direct_content(self, node: Tag) -> bool:
        for child in node.children:
            if isinstance(child, NavigableString):
                if child.strip():
                    return True
                continue
            if not isinstance(child, Tag):
                continue
            if self.section_predicate(child):
                continue
            if child.get_text(" ", strip=True):
                return True
        return False

    @staticmethod
    def _leading_heading(node: Tag) -> Tag | None:
        heading = BaseParser._leading_heading(node)
        if heading:
            return heading

        heading = node.find(
            lambda tag: isinstance(tag, Tag)
            and tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}
            and any(
                isinstance(value, str)
                and (
                    "section__title" in value.lower()
                    or "section__subtitle" in value.lower()
                    or value.lower().startswith("article-section__title")
                )
                for value in (tag.get("class") or [])
            )
        )
        if heading:
            return heading

        visited: set[str] = set()
        current: Tag | None = node
        while isinstance(current, Tag):
            labelled = current.get("aria-labelledby")
            if isinstance(labelled, str):
                for token in labelled.split():
                    identifier = token.strip()
                    if not identifier or identifier in visited:
                        continue
                    visited.add(identifier)
                    scope: Tag | None = current
                    while isinstance(scope, Tag):
                        found = scope.find(id=identifier)
                        if isinstance(found, Tag):
                            return found
                        scope = scope.parent if isinstance(scope.parent, Tag) else None
            current = current.parent if isinstance(current.parent, Tag) else None

        return None

    def _content_root(self, node: Tag) -> Tag:  # type: ignore[override]
        if node.name == "section":
            for child in node.find_all(True, recursive=False):
                classes = {
                    value.lower()
                    for value in (child.get("class") or [])
                    if isinstance(value, str)
                }
                if child.name == "div" and any(
                    class_name.startswith("article-section__content")
                    or class_name.startswith("article-section__full")
                    or class_name.startswith("article-section__body")
                    for class_name in classes
                ):
                    return self._content_root(child)
            return node

        classes = {
            value.lower() for value in (node.get("class") or []) if isinstance(value, str)
        }
        data_locator = node.get("data-test-locator") or node.get("data-testid")
        candidate_children: list[Tag] = []

        for child in node.find_all(True, recursive=False):
            if not isinstance(child, Tag):
                continue
            child_classes = {
                value.lower()
                for value in (child.get("class") or [])
                if isinstance(value, str)
            }
            child_data_locator = child.get("data-test-locator") or child.get("data-testid")
            child_locator = child_data_locator.lower() if isinstance(child_data_locator, str) else ""
            if any(
                class_name.startswith("article-section__content")
                or class_name.startswith("article-section__full")
                or class_name.startswith("article-section__sub-content")
                or class_name.startswith("accordion__panel-body")
                for class_name in child_classes
            ) or (child_locator and "article-section" in child_locator):
                candidate_children.append(child)

        if not candidate_children and isinstance(data_locator, str):
            locator = data_locator.lower()
            if "article-section" in locator:
                for descendant in node.find_all(True):
                    if not isinstance(descendant, Tag):
                        continue
                    descendant_classes = {
                        value.lower()
                        for value in (descendant.get("class") or [])
                        if isinstance(value, str)
                    }
                    descendant_data = descendant.get("data-test-locator") or descendant.get("data-testid")
                    descendant_locator = descendant_data.lower() if isinstance(descendant_data, str) else ""
                    if any(
                        class_name.startswith("article-section__content")
                        or class_name.startswith("article-section__full")
                        or class_name.startswith("article-section__sub-content")
                        or class_name.startswith("accordion__panel-body")
                        for class_name in descendant_classes
                    ) or (descendant_locator and "article-section" in descendant_locator):
                        candidate_children.append(descendant)
                        break

        for child in candidate_children:
            return self._content_root(child)

        if "accordion__panel" in classes:
            body = node.find(
                lambda tag: isinstance(tag, Tag)
                and (
                    "accordion__panel-body" in {
                        value.lower()
                        for value in (tag.get("class") or [])
                        if isinstance(value, str)
                    }
                    or (
                        isinstance(tag.get("data-test-locator"), str)
                        and "article-section" in tag.get("data-test-locator").lower()
                    )
                    or (
                        isinstance(tag.get("data-testid"), str)
                        and "article-section" in tag.get("data-testid").lower()
                    )
                )
            )
            if isinstance(body, Tag):
                return self._content_root(body)

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
            from .sciencedirect.citations import SentenceCitationAnnotator

            cls._body_extractor = WileyBodyExtractor(
                citation_annotator=SentenceCitationAnnotator(),
                section_predicate=cls._is_wiley_section,
                heading_finder=WileyBodyExtractor._leading_heading,
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
