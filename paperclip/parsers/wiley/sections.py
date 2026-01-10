from __future__ import annotations

import re
from typing import Any

from bs4 import Tag

from ...sectionizer import classify_heading, kinds_for_kind

_WS_RX = re.compile(r"\s+")

# Things that look like headings but should stop or be excluded.
_REF_HEADING_RX = re.compile(
    r"^\s*(references|bibliography|works cited|literature cited|citations)\s*$", re.I
)

# Sections that are not main text content (still within <article> often)
_SKIP_SECTION_IDS = {
    "article-references-section-1",
    "cited-by",
    "citedby-section",
}
_SKIP_CLASS_FRAGMENTS = (
    "article-section__references",
    "article-section__citedby",
    "cited-by",
    "tab__pane",  # right-rail panes sometimes get captured in messy HTML
)


def _norm_space(s: str) -> str:
    return _WS_RX.sub(" ", (s or "").strip())


def _has_bad_class(t: Tag) -> bool:
    cls = " ".join(t.get("class") or []).lower()
    return any(frag in cls for frag in _SKIP_CLASS_FRAGMENTS)


def _collect_paragraphish_text(container: Tag) -> list[str]:
    """
    Build readable text while avoiding obvious duplication.
    - Keep <p> always.
    - Include <li> only if it doesn't contain <p> descendants.
    - Fallback to container.get_text if no <p>/<li>.
    """
    out: list[str] = []

    for node in container.find_all(["p", "li"]):
        if not isinstance(node, Tag):
            continue
        if node.name == "li" and node.find("p") is not None:
            continue
        txt = _norm_space(node.get_text(" ", strip=True))
        if txt:
            out.append(txt)

    if not out:
        txt = _norm_space(container.get_text(" ", strip=True))
        if txt:
            out.append(txt)

    # De-dupe consecutive identical lines
    deduped: list[str] = []
    last = ""
    for t in out:
        if t == last:
            continue
        deduped.append(t)
        last = t

    return deduped


def _append_section(
    sections: list[dict[str, Any]],
    *,
    title: str,
    kind: str,
    level: int,
    text_lines: list[str],
) -> None:
    text = "\n".join([x for x in text_lines if x.strip()]).strip()
    if not text:
        return
    sid = f"s{len(sections)+1:02d}"
    sections.append(
        {
            "id": sid,
            "title": title,
            "kind": kind,
            "kinds": kinds_for_kind(kind),
            "level": level,
            "text": text,
        }
    )


def wiley_sections_from_html(article: Tag) -> list[dict[str, Any]]:
    """
    Wiley (Literatum) patterns:
      - Abstract: section.article-section__abstract with <p> children
      - Main: repeated section.article-section__content blocks
        - sometimes a "heading-only" block (e.g., ss3) is followed by content in next block (ss4)
          which lacks the h2 title -> we treat that as continuation.

    Returns canonical sections list matching PMC/OUP conventions.
    """
    sections: list[dict[str, Any]] = []

    # Abstract
    abs_sec = article.select_one("section.article-section__abstract")
    if isinstance(abs_sec, Tag):
        abs_lines = _collect_paragraphish_text(abs_sec)
        if abs_lines:
            _append_section(
                sections,
                title="Abstract",
                kind="abstract",
                level=2,
                text_lines=abs_lines,
            )

    content_secs = article.select("section.article-section__content")

    cur_title = ""
    cur_kind = "other"
    cur_level = 2
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, cur_title, cur_kind, cur_level
        if not buf:
            return
        title = cur_title.strip() or "Body"
        _append_section(
            sections,
            title=title,
            kind=cur_kind,
            level=cur_level,
            text_lines=buf,
        )
        buf = []

    for sec in content_secs:
        if not isinstance(sec, Tag):
            continue

        sid = str(sec.get("id") or "").strip()
        if sid in _SKIP_SECTION_IDS:
            continue
        if _has_bad_class(sec):
            continue

        # Skip embedded references/cited-by content if present
        if sec.select_one("section.article-section__references") is not None:
            continue

        # Heading for this block (if any)
        h = sec.select_one("h2.article-section__title, h2.article-section__header, h2")
        title_txt = (
            _norm_space(h.get_text(" ", strip=True)) if isinstance(h, Tag) else ""
        )

        if title_txt:
            if _REF_HEADING_RX.match(title_txt):
                flush()
                break

            flush()
            cur_title = title_txt
            cur_kind = classify_heading(cur_title)
            cur_level = 2

        # Collect text lines
        lines = _collect_paragraphish_text(sec)

        # Some pages echo the heading in text extraction; drop exact match at start.
        if title_txt and lines and lines[0].strip() == title_txt:
            lines = lines[1:]

        if lines:
            buf.extend(lines)

    flush()
    return sections
