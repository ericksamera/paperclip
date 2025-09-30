# services/server/captures/site_parsers/frontiers.py
from __future__ import annotations

import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import DOI_RE, collapse_spaces, augment_from_raw

# -------------------------- small helpers --------------------------

_HEAD_RX = re.compile(r"\b(abstract|introduction|methods?|results?|discussion)\b", re.I)
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg|conflict of interest|ethics|funding|data availability|author contributions?)\b",
    re.I,
)

def _txt(x: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (x or "").replace("\xa0", " ")).strip()

def _heading_text(h: Optional[Tag]) -> str:
    if not h:
        return ""
    t = _txt(h.get_text(" ", strip=True))
    # Strip outline numbers like "1.", "2.4", "1)"
    return re.sub(r"^\s*\d+(?:\.\d+)*\s*[\.\)]?\s*", "", t)

def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen, out = set(), []
    for k in items:
        lk = k.lower().strip()
        if lk and lk not in seen:
            seen.add(lk)
            out.append(k.strip())
    return out

def _is_heading(tag: Tag) -> bool:
    return isinstance(tag, Tag) and tag.name in {"h2", "h3", "h4"}

def _looks_like_kw_host(tag: Tag) -> bool:
    if not isinstance(tag, Tag):
        return False
    cid = (tag.get("id") or "").lower()
    cls = " ".join((tag.get("class") or [])).lower()
    return ("keyword" in cid) or ("keyword" in cls)

# -------------------------- Abstract --------------------------

def _extract_abstract(soup: BeautifulSoup) -> Optional[str]:
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
    head = soup.find(lambda t: _is_heading(t) and re.search(r"\babstract\b", _heading_text(t), re.I))
    if head:
        paras = _paras_between(head, _next_heading(head))
        if paras:
            return " ".join(paras)

    # 3) Fallback: paragraphs *above* the "Introduction" heading (Frontiers often uses loose <p> before H2)
    intro = soup.find(lambda t: _is_heading(t) and re.search(r"\bintroduction\b", _heading_text(t), re.I))
    if intro:
        out: List[str] = []
        sib = intro.previous_sibling
        steps = 0
        while sib is not None and steps < 40:
            steps += 1
            if isinstance(sib, Tag):
                if _is_heading(sib) and re.search(_HEAD_RX, _heading_text(sib)):
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

def _extract_keywords(soup: BeautifulSoup) -> List[str]:
    # Prefer structured keyword widgets when present
    for kw_wrap in soup.find_all(_looks_like_kw_host):
        items: List[str] = []
        items += [a.get_text(" ", strip=True) for a in kw_wrap.select("a, .keyword, span, li")]
        items = [re.sub(r"^\s*Keywords?\s*:\s*", "", _txt(t), flags=re.I) for t in items]
        items = [t for t in items if t and len(t) > 1]
        if items:
            return _dedupe_keep_order(items)

    # Fallback: any paragraph that starts with “Keywords:”
    p = soup.find(string=re.compile(r"^\s*Keywords?\s*:", re.I))
    if p and isinstance(p, str):
        text = re.sub(r"^\s*Keywords?\s*:\s*", "", p, flags=re.I)
        parts = [x.strip() for x in re.split(r"[;,/]|[\r\n]+", text) if x.strip()]
        if parts:
            return _dedupe_keep_order(parts)

    return []

# -------------------------- Sections --------------------------

def _paras_between(h: Tag, next_h: Optional[Tag]) -> List[str]:
    """
    Collect visible paragraph-like text nodes that appear between a heading and the next heading.
    IMPORTANT: Frontiers often places the first paragraph as a direct sibling <p> of <h2>,
    e.g. <h2>Introduction</h2><p class="mb15">…</p> — handle that explicitly.
    """
    out: List[str] = []
    sib = h.next_sibling
    while sib and sib is not next_h:
        if isinstance(sib, Tag):
            if _is_heading(sib):
                break
            # 1) direct <p> sibling (the bit we were missing)
            if sib.name == "p":
                t = _txt(sib.get_text(" ", strip=True))
                if t:
                    out.append(t)
            # 2) lists directly under the container
            elif sib.name in {"ul", "ol"}:
                for li in sib.find_all("li", recursive=True):
                    t = _txt(li.get_text(" ", strip=True))
                    if t:
                        out.append(t)
            # 3) otherwise, any nested <p> within this sibling subtree
            else:
                for p in sib.find_all("p"):
                    t = _txt(p.get_text(" ", strip=True))
                    if t:
                        out.append(t)
        sib = sib.next_sibling
    return out

def _next_heading(h: Tag) -> Optional[Tag]:
    cur = h.next_sibling
    while cur:
        if isinstance(cur, Tag) and _is_heading(cur):
            return cur
        cur = cur.next_sibling
    return None

def _extract_sections(soup: BeautifulSoup) -> List[Dict[str, object]]:
    root = soup.find("div", class_=re.compile(r"JournalFullText", re.I)) \
        or soup.find("article") or soup.find("main") or soup
    headings = [h for h in root.find_all(["h2", "h3", "h4"]) if not _NONCONTENT_RX.search(_heading_text(h))]
    if not headings:
        return []

    def level_of(tag: Tag) -> int:
        return {"h2": 2, "h3": 3, "h4": 4}.get(tag.name.lower(), 99)

    top: List[Dict[str, object]] = []
    stack: List[tuple[int, Dict[str, object]]] = []

    for i, h in enumerate(headings):
        lvl = level_of(h)
        title = _heading_text(h)
        if not title:
            continue
        next_h = None
        for k in headings[i + 1:]:
            next_h = k
            break
        node: Dict[str, object] = {"title": title, "paragraphs": _paras_between(h, next_h)}

        while stack and stack[-1][0] >= lvl:
            stack.pop()
        if stack:
            stack[-1][1].setdefault("children", []).append(node)
        else:
            top.append(node)
        stack.append((lvl, node))

    # De-dup by (title, children_count)
    seen, uniq = set(), []
    for n in top:
        key = ((n.get("title") or "").strip().lower(), len(n.get("children", []) or []))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(n)
    return uniq

# -------------------------- References (Frontiers blocks) --------------------------

def parse_frontiers(_url: str, dom_html: str) -> List[Dict[str, object]]:
    """
    Frontiers references appear as multiple
      <div class="References">
        <p class="ReferencesCopy1">…full citation text…</p>
        <p class="ReferencesCopy2"><a href="https://doi.org/...">CrossRef Full Text</a> | …</p>
      </div>
    We take the main text from ReferencesCopy1 and the DOI from any link or inline text.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: List[Dict[str, object]] = []

    def is_refs_box(tag: Tag) -> bool:
        if not isinstance(tag, Tag):
            return False
        cls = " ".join((tag.get("class") or [])).lower()
        return (tag.name in {"div", "section"}) and ("references" in cls)

    for box in soup.find_all(is_refs_box):
        # Prefer the main text line
        p1 = None
        for p in box.find_all("p", recursive=False):
            cls = " ".join((p.get("class") or [])).lower()
            if "referencescopy1" in cls:
                p1 = p
                break
        if not p1:
            # otherwise, first <p> that's not the link line
            for p in box.find_all("p", recursive=False):
                cls = " ".join((p.get("class") or [])).lower()
                if "referencescopy2" in cls:
                    continue
                p1 = p
                break

        raw = collapse_spaces(p1.get_text(" ", strip=True)) if p1 else collapse_spaces(box.get_text(" ", strip=True))
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

def extract_frontiers_meta(_url: str, dom_html: str) -> Dict[str, object]:
    """
    Returns dict with keys: abstract:str?, keywords:list[str], sections:list[dict]
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abs_text = _extract_abstract(soup)
    keywords = _extract_keywords(soup)
    sections = _extract_sections(soup)
    return {"abstract": abs_text, "keywords": keywords, "sections": sections}

# Register for both direct host and potential proxy-ish URL forms
register_meta(r"(?:^|\.)frontiersin\.org$", extract_frontiers_meta, where="host", name="Frontiers meta")
register_meta(r"frontiersin[-\.]",          extract_frontiers_meta, where="url",  name="Frontiers meta (proxy)")

# References registration
register(r"(?:^|\.)frontiersin\.org$", parse_frontiers, where="host", name="Frontiers references")
register(r"frontiersin[-\.]",          parse_frontiers, where="url",  name="Frontiers references (proxy)")
