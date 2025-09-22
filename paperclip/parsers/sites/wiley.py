from __future__ import annotations
from urllib.parse import urlparse
from typing import TYPE_CHECKING, Any, ClassVar

from bs4 import BeautifulSoup, NavigableString, Tag

from ..base import BaseParser, ReferenceObj, DOI_RE
from .sciencedirect.body import BodyExtractor

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from .sciencedirect.citations import SentenceCitationAnnotator


# -------------------------------
# Wiley-specific body extraction
# -------------------------------
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

    # -------- Helpers for section collection --------
    def _collect_top_level_sections(
        self, soup: BeautifulSoup, body_root: Tag | None
    ) -> list[Tag]:
        """
        Collect Wiley body sections in document order.

        Fixes a common Wiley pattern:
            <section class="article-section article-section__full">
               <section class="article-section__content"> ... </section>
               <section class="article-section__content"> ... </section>
            </section>

        We now intentionally avoid treating the outer __full wrapper as a section
        when it simply wraps real content sections. This prevents both the
        wrapper (no direct content) and its descendants (have a section ancestor)
        from being filtered out.
        """
        candidates: list[Tag] = []
        seen_nodes: set[int] = set()

        def section_pred(tag: Tag) -> bool:
            return self.section_predicate(tag)

        def queue_nodes(root: Tag | BeautifulSoup) -> None:
            if not isinstance(root, Tag):
                return

            if section_pred(root):
                marker = id(root)
                if marker not in seen_nodes:
                    seen_nodes.add(marker)
                    candidates.append(root)

            # include nested potential sections
            for node in root.find_all(self._SECTION_TAGS):
                if not isinstance(node, Tag):
                    continue
                marker = id(node)
                if marker in seen_nodes:
                    continue
                if not section_pred(node):
                    continue
                seen_nodes.add(marker)
                candidates.append(node)

        if body_root:
            queue_nodes(body_root)

        if not candidates:
            # fallbacks typical to Wiley
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
                # if ancestor is wrapper-only (not a "real" content container), allow promotion
                if getattr(node, "_wiley_promoted", False):
                    # already promoted
                    pass
                else:
                    continue

            # keep nodes that have direct content; otherwise, if they only wrap child sections, skip wrapper
            if not self._has_direct_content(node) and self._has_section_descendant(node):
                # This is a wrapper-only node; skip it and allow its first-level content sections to be collected.
                for child in node.find_all(self._SECTION_TAGS, recursive=False):
                    if isinstance(child, Tag) and self.section_predicate(child):
                        child._wiley_promoted = True  # marker to bypass ancestor filter above
                        top_level.append(child)
                        for descendant in child.find_all(self._SECTION_TAGS):
                            if isinstance(descendant, Tag):
                                skipped_descendants.add(id(descendant))
                # Do not add the wrapper itself
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
                # ignore nested section containers when checking for content
                continue
            # skip common non-content wrappers that shouldn't count as direct content
            child_classes = {
                c.lower() for c in (child.get("class") or []) if isinstance(c, str)
            }
            if (
                "article-table-content" in child_classes
                or "article-section__inline-figure" in child_classes
                or "figure" == child.name
            ):
                # these may have text but are structural; real paragraphs live around them
                continue
            if child.get_text(" ", strip=True):
                return True
        return False

    # -------- Heading detection tweaks --------
    @staticmethod
    def _leading_heading(node: Tag) -> Tag | None:
        heading = BaseParser._leading_heading(node)
        if heading:
            return heading

        # Wiley heading classes
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

        # ARIA-labelled headings
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

    # -------- Content root selection fixes --------
    def _content_root(self, node: Tag) -> Tag:  # type: ignore[override]
        """
        Descend into immediate content containers whether they're <div> or <section>.
        """
        def class_set(el: Tag) -> set[str]:
            return {v.lower() for v in (el.get("class") or []) if isinstance(v, str)}

        # If this node is a wrapper <section>, prefer its direct content child
        if node.name in {"section", "div"}:
            for child in node.find_all(True, recursive=False):
                if not isinstance(child, Tag):
                    continue
                classes = class_set(child)
                if child.name in {"div", "section"} and any(
                    cls.startswith("article-section__content")
                    or cls.startswith("article-section__full")
                    or cls.startswith("article-section__body")
                    or cls.startswith("article-section__sub-content")
                    or cls.startswith("accordion__panel-body")
                    for cls in classes
                ):
                    return self._content_root(child)
            # If wrapper identified by data-* locator, descend to the first matching descendant
            data_locator = node.get("data-test-locator") or node.get("data-testid")
            if isinstance(data_locator, str) and "article-section" in data_locator.lower():
                descendant = node.find(
                    lambda t: isinstance(t, Tag)
                    and t.name in {"div", "section"}
                    and any(
                        isinstance(val, str) and (
                            val.lower().startswith("article-section__content")
                            or val.lower().startswith("article-section__full")
                            or val.lower().startswith("article-section__sub-content")
                            or val.lower().startswith("accordion__panel-body")
                        )
                        for val in (t.get("class") or [])
                    )
                )
                if isinstance(descendant, Tag):
                    return self._content_root(descendant)

        # Special-case accordion panels sometimes used around body chunks
        classes = class_set(node)
        if "accordion__panel" in classes:
            body = node.find(
                lambda tag: isinstance(tag, Tag)
                and (
                    "accordion__panel-body"
                    in {v.lower() for v in (tag.get("class") or []) if isinstance(v, str)}
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

    # -------- Body root location --------
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

        # Common Wiley pattern: find the first content section and use its parent as root
        first_section = soup.select_one("section.article-section__content, div.article-section__content")
        if isinstance(first_section, Tag):
            parent = first_section.parent
            if isinstance(parent, Tag):
                return parent

        return super()._locate_body_root(soup)


# -------------------------------
# Wiley parser
# -------------------------------
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

    # ---------- Wiley section predicate (FIXED) ----------
    @classmethod
    def _is_wiley_section(cls, node: Tag) -> bool:
        """
        Identify *real* content sections while ignoring common wrappers
        and structural blocks (figures/tables) that should not split text.
        """
        if node.name not in {"section", "div"}:
            return False

        classes = {
            value.lower()
            for value in (node.get("class") or [])
            if isinstance(value, str)
        }

        # Fast rejects
        if any("abstract" in class_name for class_name in classes):
            return False
        if "article-section__inline-figure" in classes:
            return False  # figure block is not a text section
        if "article-table-content" in classes:
            return False  # table wrapper is not a section

        def has_content_descendant(n: Tag) -> bool:
            return n.find(
                lambda t: isinstance(t, Tag)
                and t.name in {"div", "section"}
                and any(
                    isinstance(v, str)
                    and (
                        v.lower().startswith("article-section__content")
                        or v.lower().startswith("article-section__sub-content")
                    )
                    for v in (t.get("class") or [])
                )
            ) is not None

        # Treat these as wrappers unless they *themselves* carry direct content without nested content blocks.
        if any(
            cn.startswith("article-section__full") or cn.startswith("article-section__body")
            for cn in classes
        ):
            # If they wrap a proper content descendant, don't consider the wrapper a section.
            if has_content_descendant(node):
                return False

        data_section_type = node.get("data-section-type")
        if isinstance(data_section_type, str) and data_section_type.lower() in {
            "body",
            "full",
            "fulltext",
            "article-body",
        }:
            # As above: only count if not just a wrapper for content
            if has_content_descendant(node):
                return False
            return True

        data_locator = node.get("data-test-locator") or node.get("data-testid")
        if isinstance(data_locator, str) and "article-section" in data_locator.lower():
            # Still guard against wrapper case
            if has_content_descendant(node) and not any(
                cn.startswith("article-section__content") or cn.startswith("article-section__sub-content")
                for cn in classes
            ):
                return False
            return True

        # Minimal/no classes: look for explicit content descendants
        if not classes:
            content = node.find(
                class_=lambda name: isinstance(name, str)
                and (name.lower().startswith("article-section__content"))
            )
            if content:
                return True

        # Positive cases
        if any(
            class_name.startswith("article-section__content")
            or class_name.startswith("article-section__sub-content")
            for class_name in classes
        ):
            return True

        if "article-section" in classes and node.find(
            class_=lambda name: isinstance(name, str)
            and name.lower().startswith("article-section__content")
        ):
            return True

        # Headings imply a real section (but avoid "abstract")
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

        # ARIA-labelled sections with headings that are not "Abstract"
        labelled = node.get("aria-labelledby")
        if isinstance(labelled, str) and labelled.strip():
            heading = node.find(id=labelled.strip())
            if isinstance(heading, Tag):
                text = heading.get_text(" ", strip=True).lower()
                if text and "abstract" not in text:
                    return True

        return False
