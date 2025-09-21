from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag

from .citations import SentenceCitationAnnotator


@dataclass
class BodyExtractor:
    citation_annotator: SentenceCitationAnnotator
    section_predicate: Callable[[Tag], bool]
    heading_finder: Callable[[Tag], Optional[Tag]]

    def extract(self, soup: BeautifulSoup) -> List[dict[str, Any]]:
        body_root = self._locate_body_root(soup)
        sections: List[Tag] = []
        if body_root:
            for child in body_root.find_all("section", recursive=False):
                if self.section_predicate(child):
                    sections.append(child)
        if not sections:
            for candidate in soup.select("section[id]"):
                if not self.section_predicate(candidate):
                    continue
                if any(
                    isinstance(parent, Tag)
                    and parent is not candidate
                    and self.section_predicate(parent)
                    for parent in candidate.parents
                ):
                    continue
                sections.append(candidate)

        results: List[dict[str, Any]] = []
        for idx, section in enumerate(sections, start=1):
            built = self._build_body_section(section, fallback_title=f"Section {idx}")
            if built:
                results.append(built)
        return results

    def _locate_body_root(self, soup: BeautifulSoup) -> Optional[Tag]:
        selectors = [
            "section.Sections",
            "section.article-body",
            "section[id^='body']",
            "div.article-body",
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if isinstance(node, Tag):
                return node
        return None

    def _build_body_section(self, node: Tag, fallback_title: Optional[str]) -> Optional[dict[str, Any]]:
        heading = self.heading_finder(node)
        title = (heading.get_text(" ", strip=True) if heading else None) or fallback_title or (node.get("id") or "").strip() or None

        html_fragments: List[str] = []
        children: List[dict[str, Any]] = []
        subsection_index = 1

        for child in node.children:
            if isinstance(child, NavigableString):
                fragment = self._normalise_body_html(child)
                if fragment:
                    html_fragments.append(fragment)
                continue
            if not isinstance(child, Tag):
                continue
            if heading and child is heading:
                continue
            if self.section_predicate(child):
                if title or fallback_title:
                    basis = title or fallback_title or "Section"
                    child_fallback = f"{basis} {subsection_index}"
                else:
                    child_fallback = f"Section {subsection_index}"
                subsection_index += 1
                built_child = self._build_body_section(child, child_fallback)
                if built_child:
                    children.append(built_child)
                continue
            fragment = self._normalise_body_html(child)
            if fragment:
                html_fragments.append(fragment)

        html_content = "".join(html_fragments).strip()
        if html_content:
            html_content = self.citation_annotator.annotate_fragment(html_content)
        if not html_content and not children:
            return None

        data: dict[str, Any] = {
            "title": title or fallback_title or "",
            "html": html_content,
        }
        if children:
            data["children"] = children
        return data

    def _normalise_body_html(self, node: Tag | NavigableString) -> str:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if not text:
                return ""
            fragment = f"<p>{html.escape(text)}</p>"
            return self.citation_annotator.annotate_fragment(fragment)
        if not isinstance(node, Tag):
            return ""
        if node.name in {"script", "style"}:
            return ""
        if self.section_predicate(node):
            return ""
        if node.name == "div":
            inner = node.decode_contents().strip()
            if not inner:
                return ""
            fragment = f"<p>{inner}</p>"
            return self.citation_annotator.annotate_fragment(fragment)
        if node.name == "p":
            return self.citation_annotator.annotate_fragment(node.decode().strip())
        return node.decode().strip()
