from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional

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
        content_root = self._content_root(node)
        heading = self.heading_finder(node)
        if heading is None and content_root is not node:
            heading = self.heading_finder(content_root)
        title = (heading.get_text(" ", strip=True) if heading else None) or fallback_title or (node.get("id") or "").strip() or None

        html_fragments: List[str] = []
        children: List[dict[str, Any]] = []
        subsection_index = 1

        for child in content_root.children:
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
        paragraphs = self._html_to_paragraphs(html_content)
        markdown = self._join_paragraph_markdown(paragraphs)

        if not markdown and not paragraphs and not children:
            return None

        data: dict[str, Any] = {
            "title": title or fallback_title or "",
            "markdown": markdown,
        }
        if paragraphs:
            data["paragraphs"] = paragraphs
        if children:
            data["children"] = children
        return data

    def _content_root(self, node: Tag) -> Tag:
        return node

    def _normalise_body_html(self, node: Tag | NavigableString) -> str:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if not text:
                return ""
            fragment = f"<p>{html.escape(text)}</p>"
            return fragment
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
            return fragment
        if node.name == "p":
            return node.decode().strip()
        return node.decode().strip()

    def _html_to_paragraphs(self, html_content: str) -> List[dict[str, Any]]:
        if not html_content:
            return []
        soup = BeautifulSoup(f"<wrapper>{html_content}</wrapper>", "html.parser")
        paragraphs: List[dict[str, Any]] = []
        for element in list(soup.wrapper.contents):
            if isinstance(element, NavigableString):
                text = self._clean_text(str(element))
                if not text:
                    continue
                markdown = self._clean_markdown(text)
                if not markdown:
                    continue
                paragraphs.append(
                    {
                        "type": "text",
                        "markdown": markdown,
                        "sentences": [{"markdown": markdown, "citations": []}],
                    }
                )
                continue
            if not isinstance(element, Tag):
                continue
            if element.name == "p":
                markdown = self._markdown_from_nodes(element.contents)
                sentences = self._sentence_segments(element)
                if not sentences and markdown:
                    sentences = [{"markdown": markdown, "citations": []}]
                if markdown or sentences:
                    paragraphs.append(
                        {
                            "type": "paragraph",
                            "markdown": markdown,
                            "sentences": sentences,
                        }
                    )
                continue
            if element.name in {"ul", "ol"}:
                ordered = element.name == "ol"
                for index, li in enumerate(element.find_all("li", recursive=False), start=1):
                    li_markdown = self._markdown_from_nodes(li.contents)
                    sentences = self._sentence_segments(li)
                    if not sentences and li_markdown:
                        sentences = [{"markdown": li_markdown, "citations": []}]
                    if not li_markdown and not sentences:
                        continue
                    prefix = f"{index}. " if ordered else "- "
                    item_markdown = f"{prefix}{li_markdown}".strip()
                    paragraphs.append(
                        {
                            "type": "list_item",
                            "list_type": "ordered" if ordered else "unordered",
                            "markdown": item_markdown,
                            "sentences": sentences,
                        }
                    )
                continue
            markdown = self._markdown_from_nodes(element.contents)
            sentences = self._sentence_segments(element)
            if not sentences and markdown:
                sentences = [{"markdown": markdown, "citations": []}]
            if not markdown and not sentences:
                continue
            paragraphs.append(
                {
                    "type": element.name,
                    "markdown": markdown,
                    "sentences": sentences,
                }
            )
        return paragraphs

    def _sentence_segments(self, block: Tag) -> List[dict[str, Any]]:
        segments: List[dict[str, Any]] = []

        def flush_buffer(buffer: List[Any]) -> None:
            if not buffer:
                return
            markdown = self._markdown_from_nodes(buffer)
            if markdown:
                segments.append({"markdown": markdown, "citations": []})
            buffer.clear()

        buffer: List[Any] = []

        for child in block.contents:
            if isinstance(child, Tag) and child.has_attr("data-citation-refs"):
                if child.find_parent(lambda p: isinstance(p, Tag) and p is not block and p.has_attr("data-citation-refs")):
                    # Skip nested citation spans; they'll be handled with the outer span.
                    buffer.append(child)
                    continue
                flush_buffer(buffer)
                refs = [ref for ref in child.get("data-citation-refs", "").split() if ref]
                markdown = self._markdown_from_nodes(child.contents)
                if markdown:
                    segments.append({"markdown": markdown, "citations": refs})
                continue
            buffer.append(child)

        flush_buffer(buffer)
        return [segment for segment in segments if segment.get("markdown")]

    def _markdown_from_nodes(self, nodes: Iterable[Tag | NavigableString]) -> str:
        parts: List[str] = []
        for node in nodes:
            parts.append(self._node_to_markdown(node))
        return self._clean_markdown("".join(parts))

    def _node_to_markdown(self, node: Tag | NavigableString) -> str:
        if isinstance(node, NavigableString):
            return self._clean_text(str(node))
        if not isinstance(node, Tag):
            return ""
        name = node.name.lower()
        if name in {"script", "style"}:
            return ""
        if node.has_attr("data-citation-refs"):
            return self._markdown_from_nodes(node.contents)
        if name in {"span", "div"}:
            return self._markdown_from_nodes(node.contents)
        if name in {"em", "i"}:
            inner = self._markdown_from_nodes(node.contents)
            return f"*{inner}*" if inner else ""
        if name in {"strong", "b"}:
            inner = self._markdown_from_nodes(node.contents)
            return f"**{inner}**" if inner else ""
        if name == "code":
            inner = self._markdown_from_nodes(node.contents)
            return f"`{inner}`" if inner else ""
        if name == "a":
            inner = self._markdown_from_nodes(node.contents)
            href = (node.get("href") or "").strip()
            if not inner:
                return ""
            if href:
                return f"[{inner}]({href})"
            return inner
        if name == "sup":
            inner = self._markdown_from_nodes(node.contents)
            return f"^{inner}" if inner else ""
        if name == "sub":
            inner = self._markdown_from_nodes(node.contents)
            return f"~{inner}" if inner else ""
        if name == "br":
            return "\n"
        if name in {"ul", "ol"}:
            items: List[str] = []
            ordered = name == "ol"
            for index, li in enumerate(node.find_all("li", recursive=False), start=1):
                item = self._markdown_from_nodes(li.contents)
                if not item:
                    continue
                prefix = f"{index}. " if ordered else "- "
                items.append(f"{prefix}{item}")
            return "\n".join(items)
        if name == "li":
            return self._markdown_from_nodes(node.contents)
        return self._markdown_from_nodes(node.contents)

    @staticmethod
    def _clean_text(value: str) -> str:
        return value.replace("\xa0", " ")

    @staticmethod
    def _clean_markdown(value: str) -> str:
        if not value:
            return ""
        text = value
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s*\n\s*", "\n", text)
        return text.strip()

    @staticmethod
    def _join_paragraph_markdown(paragraphs: List[dict[str, Any]]) -> str:
        if not paragraphs:
            return ""
        chunks: List[str] = []
        for para in paragraphs:
            chunk = para.get("markdown", "").strip()
            if not chunk:
                continue
            chunks.append(chunk)
        return "\n\n".join(chunks)
