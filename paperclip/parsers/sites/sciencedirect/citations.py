from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup


class SentenceCitationAnnotator:
    """Annotate sentences with the reference ids they mention."""

    TAG_PATTERN = re.compile(r"<[^>]+>")

    def annotate_fragment(self, html_fragment: str) -> str:
        """Return ``html_fragment`` with citation metadata spans inserted."""
        if not html_fragment:
            return html_fragment

        soup = BeautifulSoup(f"<wrapper>{html_fragment}</wrapper>", "html.parser")
        modified = False
        for block in soup.wrapper.find_all(["p", "li"], recursive=True):
            original = block.decode_contents()
            updated = self._wrap_sentence_citations(original)
            if updated == original:
                continue
            replacement = BeautifulSoup(f"<wrapper>{updated}</wrapper>", "html.parser")
            block.clear()
            for child in list(replacement.wrapper.contents):
                block.append(child)
            modified = True

        if not modified:
            return html_fragment
        return soup.wrapper.decode_contents()

    def _wrap_sentence_citations(self, html_fragment: str) -> str:
        if not html_fragment:
            return html_fragment

        tags: List[str] = []

        def _store_tag(match: re.Match[str]) -> str:
            tags.append(match.group(0))
            return f"@@TAG{len(tags) - 1}@@"

        tokenised = self.TAG_PATTERN.sub(_store_tag, html_fragment)
        sentences = self._split_sentences(tokenised)
        if not sentences:
            return html_fragment

        rebuilt: List[str] = []
        for sentence in sentences:
            refs = self._extract_sentence_references(sentence, tags)
            restored = self._restore_tokens(sentence, tags)
            if refs:
                leading_ws = re.match(r"^\s*", restored)
                trailing_ws = re.search(r"\s*$", restored)
                leading = leading_ws.group(0) if leading_ws else ""
                trailing = trailing_ws.group(0) if trailing_ws else ""
                core = restored[len(leading): len(restored) - len(trailing) if trailing else len(restored)]
                span = f'<span data-citation-refs="{" ".join(refs)}">{core}</span>'
                rebuilt.append(f"{leading}{span}{trailing}")
            else:
                rebuilt.append(restored)
        return "".join(rebuilt)

    @staticmethod
    def _restore_tokens(text: str, tags: List[str]) -> str:
        if not text:
            return text
        return re.sub(r"@@TAG(\d+)@@", lambda m: tags[int(m.group(1))], text)

    def _extract_sentence_references(self, sentence: str, tags: List[str]) -> List[str]:
        refs: List[str] = []
        seen: set[str] = set()
        for match in re.finditer(r"@@TAG(\d+)@@", sentence):
            tag_index = int(match.group(1))
            tag_text = tags[tag_index]
            ref_id = self._reference_id_from_tag(tag_text)
            if not ref_id or ref_id in seen:
                continue
            seen.add(ref_id)
            refs.append(ref_id)
        return refs

    @staticmethod
    def _reference_id_from_tag(tag_text: str) -> Optional[str]:
        if not tag_text.lower().startswith("<a"):
            return None
        href_match = re.search(r'href="#([^"#]+)"', tag_text, flags=re.I)
        if href_match:
            candidate = href_match.group(1).strip()
            if candidate and "bib" in candidate.lower():
                return candidate
        data_id_match = re.search(r'data-xocs-content-id="([^"#]+)"', tag_text, flags=re.I)
        if data_id_match:
            candidate = data_id_match.group(1).strip()
            if candidate and "bib" in candidate.lower():
                return candidate
        name_match = re.search(r'name="([^"#]+)"', tag_text, flags=re.I)
        if name_match:
            candidate = name_match.group(1).strip()
            if candidate and "bib" in candidate.lower():
                return candidate
        return None

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        sentences: List[str] = []
        start = 0
        length = len(text)
        i = 0
        while i < length:
            char = text[i]
            if char in ".?!":
                j = i + 1
                while j < length and text[j] in ")\"]":
                    j += 1
                next_char = text[j] if j < length else ""
                next_token = text[j:j + 6]
                if j >= length or next_char.isspace() or next_token.startswith("@@TAG"):
                    segment = text[start:j]
                    if segment:
                        sentences.append(segment)
                    while j < length and text[j].isspace():
                        sentences.append(text[j])
                        j += 1
                    start = j
                    i = j
                    continue
            i += 1
        if start < length:
            sentences.append(text[start:])
        return sentences
