# services/server/captures/site_parsers/pmc.py
from __future__ import annotations

import re
from typing import Dict, List, Optional, Iterable
from bs4 import BeautifulSoup, Tag, NavigableString

from . import register, register_meta
from .base import (
    extract_from_li, augment_from_raw,            # references helpers
    heading_text, dedupe_keep_order,              # titles & de-dupe
    collect_paragraphs_subtree,                   # safe fallback (guarded)
    split_keywords_block, KEYWORDS_PREFIX_RX,     # keywords helpers
    dedupe_section_nodes,                         # section de-dupe
)

# ======================================================================================
# References
# ======================================================================================

def parse_pmc(url: str, dom_html: str) -> List[Dict[str, object]]:
    """
    Extracts references from PMC-style pages. Works for both:
      - <section id="ref-list..." class="ref-list"><ol class="ref-list">...</ol></section>
      - any <ol/ul class="ref-list">...</ol/ul> structure
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    refs: List[Dict[str, object]] = []

    # Primary: anything under a ref-list section or list with class "ref-list"
    for li in soup.select("section.ref-list li, .ref-list li, ol.ref-list li, ul.ref-list li"):
        if not li.get_text(strip=True):
            continue
        base = extract_from_li(li)
        refs.append(augment_from_raw(base))

    # Fallback: generic "references" lists
    if not refs:
        for li in soup.select("ol.references li, ul.references li"):
            if not li.get_text(strip=True):
                continue
            base = extract_from_li(li)
            refs.append(augment_from_raw(base))

    return refs


# Route by host AND by url path (references)
register(r"(?:^|\.)pmc\.ncbi\.nlm\.nih\.gov$", parse_pmc, where="host", name="PMC host")
register(r"ncbi\.nlm\.nih\.gov/.*/pmc/|/pmc/", parse_pmc, where="url",  name="PMC path")


# ======================================================================================
# Meta / Sections
# ======================================================================================

# Common non-content section headings to skip
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg(e)?ments?|author(?:s)?(?:[’'\s]|\s*contributions?)|"
    r"funding|competing interests?|conflicts? of interest|ethics|data availability|"
    r"declarations?|footnotes?|contributor information|supplementary(?: information)?|"
    r"associated data)\b",
    re.I,
)

def _txt(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


# --------------------------------------------------------------------------------------
# Keywords detection helpers (more robust than PMC-only English "Keywords:" lines)
# --------------------------------------------------------------------------------------

# Widely seen "Keywords" headings/labels on PMC and mirrored journals (English + a few common langs)
_KEYWORDS_LABEL_RX = re.compile(
    r"^\s*(keywords?|key\s*words?|"
    r"mots[\s-]*clés?|"
    r")\s*[:：]?\s*$",
    re.I,
)

_EXTRA_KWD_SEP_RX = re.compile(
    r"""\s*[
        ,;:/|\\                      # ASCII punctuation
        \u2010-\u2015\u2212\u2043    # hyphen, en/em/figure/horizontal bar, minus, hyphen bullet
        \u2022\u2027\u00B7\u2219\u30FB  # bullets & middle dots
        \u3001\uFF0C\uFF1B\uFF0F       # 、 fullwidth comma/semicolon/solidus
    ]+\s*""",
    re.UNICODE | re.VERBOSE
)

def _is_keywords_line(text: str) -> bool:
    t = _txt(text)
    if not t:
        return False
    # Either our broader label regex OR the shared base KEYWORDS_PREFIX_RX (if it matches at line start)
    return bool(_KEYWORDS_LABEL_RX.match(t) or KEYWORDS_PREFIX_RX.match(t))

def _strip_keywords_label(text: str) -> str:
    t = _txt(text)
    # Remove known prefixes like "Keywords:" (from base) and our wider label set
    t = re.sub(KEYWORDS_PREFIX_RX, "", t)
    t = re.sub(r"^\s*(?:keywords?|key\s*words?)\s*[:：]\s*", "", t, flags=re.I)
    return t

def _split_keywords(text: str) -> List[str]:
    """
    Use the project's splitter first; then apply a permissive extra split to catch bullets/pipes/etc.
    """
    base_items = [i for i in split_keywords_block(_strip_keywords_label(text)) if i]
    out: List[str] = []
    for item in base_items:
        parts = [p for p in _EXTRA_KWD_SEP_RX.split(item) if p]
        if parts:
            out.extend(parts)
        else:
            out.append(item)
    # Normalize, dedupe, and filter trivial tokens
    cleaned = []
    seen_lower = set()
    for i in (re.sub(r"\s+", " ", it).strip(" .:;,-") for it in out):
        if not i or len(i) < 2:
            continue
        low = i.lower()
        if low not in seen_lower:
            cleaned.append(i)
            seen_lower.add(low)
    return cleaned


# ------------------------ Abstract ------------------------

def _abstract_block(soup: BeautifulSoup) -> Optional[Tag]:
    """
    Find the abstract container on PMC pages. Handles variants like:
      - <section class="abstract" id="Abs1">...</section>
      - <section class="abstract" id="abstract1">...</section>
      - <div class="abstract">...</div>
      - H2/H3/H4 titled "Abstract"
    """
    # Common PMC abstract containers
    for sel in [
        "section.abstract", "section#Abs1", "section[id^='abs' i]",
        "div.abstract", "div#Abs1", "div[id^='abs' i]",
    ]:
        el = soup.select_one(sel)
        if el:
            return el

    # Fallback: H2/strong title “Abstract”
    for h in soup.find_all(["h2", "h3", "h4"]):
        if re.fullmatch(r"\s*abstract\s*", heading_text(h), re.I):
            return h.parent if isinstance(h.parent, Tag) else h

    return None


def _extract_pmc_abstract(soup: BeautifulSoup) -> Optional[str]:
    """
    Collect paragraphs from the abstract block, explicitly skipping the inline keywords
    block (e.g. <section class="kwd-group"> with "<strong>Keywords:</strong> ..."),
    which often sits inside the abstract container in PMC.
    """
    host = _abstract_block(soup)
    if not host:
        return None

    paras: List[str] = []
    for p in host.find_all("p"):
        # Skip any <p> that sits inside a keywords container (kwd-group),
        # or that itself is a "Keywords:" line.
        if p.find_parent(class_=re.compile(r"\bkwd-group\b", re.I)):
            continue
        t = _txt(p.get_text(" ", strip=True))
        if not t:
            continue
        if KEYWORDS_PREFIX_RX.match(t) or _KEYWORDS_LABEL_RX.match(t):
            continue
        paras.append(t)

    return " ".join(paras) if paras else None


# ------------------------ Keywords ------------------------

def _harvest_keywords_from_host(host: Tag) -> List[str]:
    """
    Pull keywords out of a given 'kwd-group' (or similar) container.
    Supports list and inline formats.
    """
    items: List[str] = []

    # List style: <ul><li>…</li></ul> or <ol>…
    for li in host.select("li"):
        t = _txt(li.get_text(" ", strip=True))
        if t:
            items.extend(_split_keywords(t))

    # Inline paragraph style like: "<p><strong>Keywords:</strong> term1, term2 …</p>"
    for p in host.find_all("p"):
        t = _txt(p.get_text(" ", strip=True))
        if not t:
            continue
        if _is_keywords_line(t) or any(ch in t for ch in (",", ";", "/", "|", "•", "·", "・")):
            items.extend(_split_keywords(t))

    # Sometimes keywords are placed into spans/anchors
    for el in host.select("a, span"):
        t = _txt(el.get_text(" ", strip=True))
        if t and not _is_keywords_line(t):
            items.extend(_split_keywords(t))

    return items


def _extract_pmc_keywords(soup: BeautifulSoup) -> List[str]:
    """
    Extract keywords from standard PMC keyword locations, including inline
    (<p><strong>Keywords:</strong> ...</p>), list formats, headings titled "Keywords",
    and a few common non-English labels. Also falls back to <meta> tags (citation_keywords/DC).
    """
    items: List[str] = []

    # Primary containers used by PMC (incl. when nested inside Abstract)
    keyword_hosts = soup.select(
        "section.kwd-group, div.kwd-group, #kwd-group, [id^='kwd-group'], "
        ".kwd-group, [class*='kwd' i], [class*='keyword' i]"
    )
    for host in keyword_hosts:
        items.extend(_harvest_keywords_from_host(host))

    # Headings literally named "Keywords" (or language variants) with content right after them
    # e.g., <h3>Keywords</h3><p>…</p> or <ul><li>…</li></ul>
    if not items:
        for h in soup.find_all(["h2", "h3", "h4"]):
            ht = heading_text(h)
            if _KEYWORDS_LABEL_RX.match(ht or ""):
                sib = h.find_next_sibling()
                while sib and isinstance(sib, (Tag, NavigableString)):
                    if isinstance(sib, Tag) and sib.name in ("h2", "h3", "h4"):
                        break  # stop at next section heading
                    if isinstance(sib, Tag):
                        # harvest text from immediate paragraph/list siblings
                        if sib.name in ("p", "div"):
                            t = _txt(sib.get_text(" ", strip=True))
                            if t:
                                items.extend(_split_keywords(t))
                        for li in sib.find_all("li"):
                            t = _txt(li.get_text(" ", strip=True))
                            if t:
                                items.extend(_split_keywords(t))
                    sib = sib.next_sibling

    # Fallback 1: a stray "Keywords:" paragraph anywhere
    if not items:
        for p in soup.find_all(["p", "div"]):
            t = _txt(p.get_text(" ", strip=True))
            if _is_keywords_line(t):
                items.extend(_split_keywords(t))

    # Fallback 2: <meta …> variants commonly used in PMC mirrors
    if not items:
        for m in soup.select(
            'meta[name*="keyword" i], meta[name="dc.Subject" i], meta[name="citation_keywords" i]'
        ):
            content = _txt(m.get("content"))
            if content:
                items.extend(_split_keywords(content))

    # Final cleanup & de-dupe
    items = [_txt(i) for i in items if i and len(i) > 1]
    items = [i for i in items if not _is_keywords_line(i)]
    return dedupe_keep_order(items)


# ------------------------ Sections ------------------------

def _paras_excluding_child_sections(sec: Tag) -> List[str]:
    """
    Collect <p>/<li> that belong to THIS section, skipping those inside nested <section> children.
    """
    out: List[str] = []

    for p in sec.find_all("p"):
        par_sec = p.find_parent("section")
        if par_sec is not None and par_sec is not sec:
            continue
        t = _txt(p.get_text(" ", strip=True))
        if t:
            out.append(t)

    for li in sec.find_all("li"):
        li_sec = li.find_parent("section")
        if li_sec is not None and li_sec is not sec:
            continue
        t = _txt(li.get_text(" ", strip=True))
        if t:
            out.append(t)

    return out


def _parse_pmc_section(sec: Tag) -> Optional[Dict[str, object]]:
    """
    Turn a <section> into a structured node: {title, paragraphs?, children?}
    """
    h = (
        sec.find(["h2", "h3", "h4"], class_=re.compile(r"pmc_sec_title", re.I))
        or sec.find(["h2", "h3", "h4"])
    )
    title = heading_text(h) if h else ""
    if not title or _NONCONTENT_RX.search(title) or re.fullmatch(r"\s*abstract\s*", title, re.I):
        return None

    # Paragraphs that belong to THIS section (exclude nested subsections)
    paras = _paras_excluding_child_sections(sec)

    # 🚫 Do NOT fall back to subtree text if the section has immediate subsections.
    has_immediate_subsections = bool(sec.find_all("section", recursive=False))
    if not paras and not has_immediate_subsections:
        # Conservative fallback only when there are no subsection children at all.
        paras = [t for t in collect_paragraphs_subtree(sec) if t]

    node: Dict[str, object] = {"title": title, "paragraphs": paras}

    # Children: any immediate subsection <section> under this section
    children: List[Dict[str, object]] = []
    for child in sec.find_all("section", recursive=False):
        kid = _parse_pmc_section(child)
        if kid and (kid.get("title") or kid.get("paragraphs") or kid.get("children")):
            children.append(kid)
    if children:
        node["children"] = children

    # Keep the node if it has something useful
    if node.get("title") or node.get("paragraphs") or node.get("children"):
        return node
    return None


def _extract_pmc_sections(soup: BeautifulSoup) -> List[Dict[str, object]]:
    """
    Build a section tree from PMC body. Robust to:
      - lowercased ids like id="sec1", id="sec2", ...
      - top-level H3/H4 headings accidentally used at top-level (e.g., "sec5" with <h3>)
      - presence of Abstract/References blocks among siblings
    """
    # Locate the main document wrapper
    wrapper = (
        soup.select_one("section.body.main-article-body")
        or soup.select_one("section#main-article-body")
        or soup.find("article")
        or soup.find("main")
        or soup
    )

    top_secs: List[Tag] = []

    # Preferred: top-level <section> elements (direct children) with some heading
    # (PMC usually nests H2s at top-level, but some pages use H3/H4 for top blocks).
    for s in wrapper.find_all("section", recursive=False):
        h = (
            s.find(["h2", "h3", "h4"], class_=re.compile(r"pmc_sec_title", re.I))
            or s.find(["h2", "h3", "h4"])
        )
        if h:
            top_secs.append(s)

    # Fallback: Any <section id="sec…"> in the document (case-insensitive), keeping only
    # those NOT nested under another "sec…" section (i.e., synthetic top-levels).
    if not top_secs:
        for s in wrapper.find_all("section", id=re.compile(r"^sec", re.I)):
            # Must have SOME heading to be meaningful
            h = (
                s.find(["h2", "h3", "h4"], class_=re.compile(r"pmc_sec_title", re.I))
                or s.find(["h2", "h3", "h4"])
            )
            if not h:
                continue

            # Exclude subsections nested under another "sec…" section
            parent = s.find_parent("section")
            keep = True
            while parent and parent is not wrapper:
                if re.match(r"^sec", (parent.get("id") or ""), re.I):
                    keep = False
                    break
                parent = parent.find_parent("section")
            if keep:
                top_secs.append(s)

    # Parse each top-level section into a node
    nodes: List[Dict[str, object]] = []
    for sec in top_secs:
        node = _parse_pmc_section(sec)
        if node:
            nodes.append(node)

    # Normalized de-duplication
    return dedupe_section_nodes(nodes)


def extract_pmc_meta(_url: str, dom_html: str) -> Dict[str, object]:
    """
    Return {"abstract": str|None, "keywords": [str], "sections": [ {title, paragraphs, children?} ]}.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abstract = _extract_pmc_abstract(soup)
    keywords = _extract_pmc_keywords(soup)
    sections = _extract_pmc_sections(soup)
    return {"abstract": abstract, "keywords": keywords, "sections": sections}


# Register meta/sections at import time so the router always has PMC headers.
register_meta(r"(?:^|\.)pmc\.ncbi\.nlm\.nih\.gov$", extract_pmc_meta, where="host", name="PMC meta")
register_meta(r"ncbi\.nlm\.nih\.gov/.*/pmc/|/pmc/", extract_pmc_meta, where="url",  name="PMC meta (path)")
