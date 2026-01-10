from __future__ import annotations

import re
from typing import Any

from bs4 import Tag

from ...sectionizer import classify_heading, kinds_for_kind

_WS_RX = re.compile(r"\s+")

# Direct-children blocks inside widget-items we want as “body” content.
_ALLOWED_BLOCK_TAGS = {"p", "div", "section"}

# Blocks/classes that are *inside* the fulltext stream but are not content.
_SKIP_CLASS_FRAGMENTS = (
    "article-metadata",
    "kwd-group",
    "metadata-taggedcollection",
    "article-metadata-tocsections",
    "copyright",
    "license",
    "toolbar",
    "downloadimagesppt",
)

# UI strings to drop if they show up in captions/links
_DROP_TEXT_RX = re.compile(
    r"^(open in new tab|download slide|download all slides|view large|open in another window)$",
    re.I,
)


def _norm_space(s: str) -> str:
    return _WS_RX.sub(" ", (s or "").strip())


def _has_bad_class(t: Tag) -> bool:
    cls = " ".join(t.get("class") or []).lower()
    return any(frag in cls for frag in _SKIP_CLASS_FRAGMENTS)


def _is_heading(t: Tag) -> bool:
    if not isinstance(t, Tag) or t.name != "h2":
        return False
    cls = " ".join(t.get("class") or []).lower()
    return (
        "abstract-title" in cls
        or "section-title" in cls
        or "backreferences-title" in cls
    )


def _heading_kind_and_title(h: Tag) -> tuple[str, str]:
    cls = " ".join(h.get("class") or []).lower()
    title = _norm_space(h.get_text(" ", strip=True))
    if "abstract-title" in cls:
        return "abstract", "Abstract"
    # backreferences-title == References (we stop before it)
    return classify_heading(title), title


def _collect_text_from_block(block: Tag) -> list[str]:
    """
    Extract readable text from a block, skipping obvious UI/duplicate noise.
    """
    out: list[str] = []

    # Prefer paragraphs
    for p in block.find_all("p", recursive=True):
        if not isinstance(p, Tag):
            continue
        txt = _norm_space(p.get_text(" ", strip=True))
        if txt and not _DROP_TEXT_RX.match(txt):
            out.append(txt)

    # Some content is in div.block-child-p without <p> children
    if not out:
        txt = _norm_space(block.get_text(" ", strip=True))
        if txt and not _DROP_TEXT_RX.match(txt):
            out.append(txt)

    return out


def _collect_section_text(nodes: list[Tag]) -> str:
    parts: list[str] = []

    for n in nodes:
        if not isinstance(n, Tag):
            continue
        if n.name not in _ALLOWED_BLOCK_TAGS:
            continue
        if _has_bad_class(n):
            continue

        # Hard-skip ref list/table of references in the stream
        cls = " ".join(n.get("class") or []).lower()
        if "ref-list" in cls:
            continue

        parts.extend(_collect_text_from_block(n))

    # De-dupe consecutive identical lines
    deduped: list[str] = []
    last = ""
    for p in parts:
        if p == last:
            continue
        deduped.append(p)
        last = p

    return "\n".join(deduped).strip()


def oup_sections_from_html(root: Tag) -> list[dict[str, Any]]:
    """
    OUP (Oxford Academic / Silverchair) HTML-first section extraction.

    Assumes `root` is the ArticleFulltext widget-items container.
    """
    if not isinstance(root, Tag):
        return []

    # Only work off the direct stream of widget-items; this avoids author/meta/metrics bleed.
    children = [c for c in root.children if isinstance(c, Tag)]
    if not children:
        return []

    # Find headings in direct children order
    heading_idxs: list[int] = [i for i, c in enumerate(children) if _is_heading(c)]
    if not heading_idxs:
        return []

    sections: list[dict[str, Any]] = []

    def next_id() -> str:
        return f"s{len(sections)+1:02d}"

    for pos, h_i in enumerate(heading_idxs):
        h = children[h_i]
        if not isinstance(h, Tag):
            continue

        # Stop at References heading
        h_cls = " ".join(h.get("class") or []).lower()
        if "backreferences-title" in h_cls:
            break

        start = h_i + 1
        end = heading_idxs[pos + 1] if pos + 1 < len(heading_idxs) else len(children)
        chunk = children[start:end]

        kind, title = _heading_kind_and_title(h)
        text = _collect_section_text(chunk)
        if not text:
            continue

        sections.append(
            {
                "id": next_id(),
                "kind": kind,
                "kinds": kinds_for_kind(kind),
                "level": 2,
                "title": title,
                "text": text,
            }
        )

    return sections
