# services/server/captures/site_parsers/frontiers.py
from __future__ import annotations

import re
from typing import cast

from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import (
    DOI_RE,
    augment_from_raw,
    collapse_spaces,
    dedupe_keep_order,
    dedupe_section_nodes,
    heading_text,
    is_heading,
    paras_between,
)

# -------------------------- small helpers --------------------------
_HEAD_RX = re.compile(r"\b(abstract|introduction|methods?|results?|discussion)\b", re.I)
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg|conflict of interest|ethics|funding|data availability|"
    r"author contributions?)\b",
    re.I,
)


def _txt(x: str | None) -> str:
    return collapse_spaces(x)


def _looks_like_kw_host(tag: Tag) -> bool:
    if not isinstance(tag, Tag):
        return False
    cid = (tag.get("id") or "").lower()
    cls = " ".join(tag.get("class") or []).lower()
    return ("keyword" in cid) or ("keyword" in cls)


# -------------------------- Abstract --------------------------
def _next_heading(h: Tag) -> Tag | None:
    cur = h.next_sibling
    while cur:
        if isinstance(cur, Tag) and is_heading(cur):
            return cur
        cur = cur.next_sibling
    return None


def _extract_abstract(soup: BeautifulSoup) -> str | None:
    # 1) Explicit abstract containers
    for host in soup.select(
        "section#abstract, section[id^='abstract' i], div#abstract, "
        "section[class*='abstract' i], div[class*='abstract' i]"
    ):
        paras = [p.get_text(" ", strip=True) for p in host.find_all("p")]
        paras = [_txt(p) for p in paras if p and len(p.strip()) > 1]
        if paras:
            return " ".join(paras)
    # 2) Heading "Abstract" → paragraphs until next heading
    head = soup.find(lambda t: is_heading(t) and re.search(r"\babstract\b", heading_text(t), re.I))
    if head:
        paras = paras_between(head, _next_heading(head))
        if paras:
            return " ".join(paras)
    # 3) Fallback: paragraphs *above* the "Introduction" heading
    intro = soup.find(
        lambda t: is_heading(t) and re.search(r"\bintroduction\b", heading_text(t), re.I)
    )
    if intro:
        out: list[str] = []
        sib = intro.previous_sibling
        steps = 0
        while sib is not None and steps < 40:
            steps += 1
            if isinstance(sib, Tag):
                if is_heading(sib) and re.search(_HEAD_RX, heading_text(sib)):
                    break
                if sib.name == "p":
                    t = _txt(sib.get_text(" ", strip=True))
                    if t and len(t) > 40:
                        out.append(t)
            sib = sib.previous_sibling
        out = list(reversed(out))
        if out:
            return " ".join(out[:4])
    return None


# -------------------------- Keywords --------------------------
def _extract_keywords(soup: BeautifulSoup) -> list[str]:
    # Prefer structured keyword widgets when present
    for kw_wrap in soup.find_all(_looks_like_kw_host):
        items: list[str] = []
        items += [a.get_text(" ", strip=True) for a in kw_wrap.select("a, .keyword, span, li")]
        items = [re.sub(r"^\s*Keywords?\s*:\s*", "", _txt(t), flags=re.I) for t in items]
        items = [t for t in items if t and len(t) > 1]
        if items:
            return dedupe_keep_order(items)
    # Fallback: any paragraph that starts with "Keywords:"
    p = soup.find(string=re.compile(r"^\s*Keywords?\s*:", re.I))
    if p and isinstance(p, str):
        text = re.sub(r"^\s*Keywords?\s*:\s*", "", p, flags=re.I)
        parts = [x.strip() for x in re.split(r"[;,/]|[\r\n]+", text) if x.strip()]
        if parts:
            return dedupe_keep_order(parts)
    return []


# -------------------------- Sections --------------------------
def _extract_sections(soup: BeautifulSoup) -> list[dict[str, object]]:
    root = (
        soup.find("div", class_=re.compile(r"JournalFullText", re.I))
        or soup.find("article")
        or soup.find("main")
        or soup
    )
    headings = [
        h for h in root.find_all(["h2", "h3", "h4"]) if not _NONCONTENT_RX.search(heading_text(h))
    ]
    if not headings:
        return []

    def level_of(tag: Tag) -> int:
        return {"h2": 2, "h3": 3, "h4": 4}.get(tag.name.lower(), 99)

    top: list[dict[str, object]] = []
    stack: list[tuple[int, dict[str, object]]] = []
    for i, h in enumerate(headings):
        lvl = level_of(h)
        title = heading_text(h)
        if not title:
            continue
        next_h = None
        for k in headings[i + 1 :]:
            next_h = k
            break
        node: dict[str, object] = {"title": title, "paragraphs": paras_between(h, next_h)}
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        if stack:
            children = cast(list[dict[str, object]], stack[-1][1].setdefault("children", []))
            children.append(node)
        else:
            top.append(node)
        stack.append((lvl, node))
    return dedupe_section_nodes(top)


# -------------------------- References (Frontiers blocks) --------------------------
def parse_frontiers(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Frontiers references appear as multiple <div class="References"> ... </div> blocks.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: list[dict[str, object]] = []

    def is_refs_box(tag: Tag) -> bool:
        if not isinstance(tag, Tag):
            return False
        cls = " ".join(tag.get("class") or []).lower()
        return (tag.name in {"div", "section"}) and ("references" in cls)

    for box in soup.find_all(is_refs_box):
        # Prefer the main text line
        p1 = None
        for p in box.find_all("p", recursive=False):
            cls = " ".join(p.get("class") or []).lower()
            if "referencescopy1" in cls:
                p1 = p
                break
        if not p1:
            # otherwise, first <p> that's not the link line
            for p in box.find_all("p", recursive=False):
                cls = " ".join(p.get("class") or []).lower()
                if "referencescopy2" in cls:
                    continue
                p1 = p
                break
        raw = (
            collapse_spaces(p1.get_text(" ", strip=True))
            if p1
            else collapse_spaces(box.get_text(" ", strip=True))
        )
        if not raw:
            continue
        # DOI: any DOI-looking href or text in the block
        doi = ""
        for a in box.find_all("a", href=True):
            m = DOI_RE.search(a.get("href", "")) or DOI_RE.search(a.get_text(" ", strip=True))
            if m:
                doi = m.group(0)
                break
        if not doi:
            m = DOI_RE.search(raw)
            if m:
                doi = m.group(0)
        base = {"raw": raw, "doi": doi}
        out.append(augment_from_raw(base))
    return out


# -------------------------- public entry (meta/sections) --------------------------
def extract_frontiers_meta(_url: str, dom_html: str) -> dict[str, object]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abs_text = _extract_abstract(soup)
    keywords = _extract_keywords(soup)
    sections = _extract_sections(soup)
    return {"abstract": abs_text, "keywords": keywords, "sections": sections}


# Register for both direct host and potential proxy-ish URL forms
register_meta(
    r"(?:^|\.)frontiersin\.org$", extract_frontiers_meta, where="host", name="Frontiers meta"
)
register_meta(
    r"frontiersin[-\.]", extract_frontiers_meta, where="url", name="Frontiers meta (proxy)"
)
# References registration
register(r"(?:^|\.)frontiersin\.org$", parse_frontiers, where="host", name="Frontiers references")
register(r"frontiersin[-\.]", parse_frontiers, where="url", name="Frontiers references (proxy)")
