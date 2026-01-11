from __future__ import annotations

import re
from typing import Any, Iterable

from bs4 import Tag

from ...sectionizer import _split_heading_number, classify_heading, kinds_for_kind

_WS_RX = re.compile(r"\s+")
_TABLE_LABEL_RX = re.compile(r"^\s*(table|figure)\s*\d+\s*\.?\s*", re.I)


def _norm_space(s: str) -> str:
    return _WS_RX.sub(" ", (s or "").strip())


def _is_bibliography_or_citedby(node: Tag) -> bool:
    cls = " ".join(node.get("class") or []).lower()
    sid = str(node.get("id") or "").lower()
    if "bibliography" in cls:
        return True
    if "listarticles" in cls or "cited-by" in cls:
        return True
    if sid.startswith("aep-bibliography"):
        return True
    if sid.startswith("section-cited-by") or sid == "section-cited-by":
        return True
    return False


def _iter_heading_nodes(root: Tag) -> Iterable[Tag]:
    for h in root.find_all(["h2", "h3", "h4"], recursive=True):
        if isinstance(h, Tag):
            yield h


def _heading_level(h: Tag) -> int:
    name = (h.name or "").lower()
    if name == "h2":
        return 2
    if name == "h3":
        return 3
    if name == "h4":
        return 4
    return 2


def _is_para_div(d: Tag) -> bool:
    if d.name != "div":
        return False
    cls = " ".join(d.get("class") or []).lower()
    return "u-margin-s-bottom" in cls


def _is_inside(node: Tag, ancestor: Tag) -> bool:
    try:
        for p in node.parents:
            if p is ancestor:
                return True
        return False
    except Exception:
        return False


def _closest_section(node: Tag) -> Tag | None:
    try:
        for p in node.parents:
            if isinstance(p, Tag) and p.name == "section":
                return p
    except Exception:
        return None
    return None


def _table_caption_lines(table_div: Tag) -> list[str]:
    """
    ScienceDirect tables often look like:
      <div class="tables ..." id="tbl1">
        <span class="captions"><p><span class="label">Table 1</span>. ...</p></span>
        <div class="groups"><table>...</table></div>
      </div>

    We keep a compact caption line and ignore the table body.
    """
    cap = table_div.select_one(".captions") or table_div.find("caption")
    if not isinstance(cap, Tag):
        return []
    txt = _norm_space(cap.get_text(" ", strip=True))
    if not txt:
        return []
    # normalize "Table 1 . X" => "Table 1. X"
    txt = txt.replace(" . ", ". ")
    return [txt]


def _collect_text_until_next_heading(
    *,
    root: Tag,
    start_heading: Tag,
    next_heading: Tag | None,
) -> list[str]:
    """
    Collect paragraph-ish text + table captions that appear after start_heading
    and before next_heading (in document order).
    """
    out: list[str] = []

    # We only want content that is *after* start_heading.
    # We'll walk forward via .next_elements until we hit next_heading (or exhaust).
    for el in start_heading.next_elements:
        if not isinstance(el, Tag):
            continue

        if next_heading is not None and el is next_heading:
            break

        # Skip whole bibliography/cited-by subtrees if they appear (defensive).
        if el.name == "section" and _is_bibliography_or_citedby(el):
            continue
        if _closest_section(el) and _is_bibliography_or_citedby(_closest_section(el)):  # type: ignore[arg-type]
            continue

        # Stop collecting if we somehow leave root
        if not _is_inside(el, root):
            break

        # Tables: keep caption, skip body noise
        if el.name == "div":
            cls = " ".join(el.get("class") or []).lower()
            if "tables" in cls:
                out.extend(_table_caption_lines(el))
                continue

        # Paragraph text
        if el.name == "p":
            txt = _norm_space(el.get_text(" ", strip=True))
            if txt:
                out.append(txt)
            continue

        # SD uses <div class="u-margin-s-bottom"> as paragraph containers
        if _is_para_div(el):
            txt = _norm_space(el.get_text(" ", strip=True))
            if txt and not _TABLE_LABEL_RX.match(txt):
                out.append(txt)
            continue

    # De-dupe consecutive identical lines
    deduped: list[str] = []
    prev = ""
    for t in out:
        if t == prev:
            continue
        deduped.append(t)
        prev = t
    return deduped


def _append_section(
    sections: list[dict[str, Any]],
    *,
    title: str,
    level: int,
    text_lines: list[str],
) -> None:
    text = "\n".join([t for t in text_lines if t.strip()]).strip()
    if not text:
        return

    num, clean_title = _split_heading_number(title)
    kind = classify_heading(clean_title)

    sid = f"s{len(sections) + 1:02d}"
    out: dict[str, Any] = {
        "id": sid,
        "title": clean_title,
        "kind": kind,
        "kinds": kinds_for_kind(kind),
        "level": int(level),
        "text": text,
    }
    if num:
        out["number"] = num
    sections.append(out)


def sciencedirect_sections_from_html(
    *, body_root: Tag, abstract_root: Tag | None
) -> list[dict[str, Any]]:
    """
    ScienceDirect section extractor (robust to nested <section> structures).

    Strategy:
      - Add Abstract (if present)
      - Use heading boundaries (h2/h3/h4) to define sections
      - Within each heading region, collect:
          * <p>
          * <div class="u-margin-s-bottom"> (paragraph-ish)
          * table captions from <div class="tables ..."> (drop table body noise)
    """
    sections: list[dict[str, Any]] = []

    # Abstract: keep it as its own section if present
    if isinstance(abstract_root, Tag):
        # Collect <p> and u-margin-s-bottom divs inside abstract_root
        abs_lines: list[str] = []
        for el in abstract_root.find_all(["p", "div"], recursive=True):
            if not isinstance(el, Tag):
                continue
            if el.name == "p" or _is_para_div(el):
                txt = _norm_space(el.get_text(" ", strip=True))
                if txt:
                    abs_lines.append(txt)
        # Dedup consecutive
        ded: list[str] = []
        prev = ""
        for t in abs_lines:
            if t == prev:
                continue
            ded.append(t)
            prev = t
        _append_section(sections, title="Abstract", level=2, text_lines=ded)

    # Headings inside the (already-pruned) content root
    headings = [h for h in _iter_heading_nodes(body_root)]
    if not headings:
        return sections

    for i, h in enumerate(headings):
        if not isinstance(h, Tag):
            continue

        # Skip headings that live under bibliography/cited-by blocks (defensive)
        sec = _closest_section(h)
        if isinstance(sec, Tag) and _is_bibliography_or_citedby(sec):
            continue

        title = _norm_space(h.get_text(" ", strip=True))
        if not title:
            continue

        nxt = headings[i + 1] if (i + 1) < len(headings) else None
        lines = _collect_text_until_next_heading(
            root=body_root, start_heading=h, next_heading=nxt
        )

        _append_section(
            sections,
            title=title,
            level=_heading_level(h),
            text_lines=lines,
        )

    return sections
