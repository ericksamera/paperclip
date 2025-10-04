# services/server/captures/site_parsers/oup.py
from __future__ import annotations

import re
from collections.abc import Iterator
from typing import cast

from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import (
    DOI_RE,
    YEAR_RE,
    augment_from_raw,
    collapse_spaces,
    dedupe_keep_order,
    dedupe_section_nodes,
    extract_from_li,
    heading_text,
)

# -------------------------- small helpers --------------------------
_NONCONTENT_RX = re.compile(
    r"\b("
    r"references?|literature\s+cited|acknowledg(?:e)?ments?|back\s*acknowledgements?|"
    r"conflicts?\s+of\s+interest|competing\s+interests?|ethics|funding|data\s+availability|"
    r"author(?:s)?\s+contributions?|footnotes?|supplementary(?:\s+material|\s+information)?)\b",
    re.I,
)
# containers we should not treat as narrative body
_EXCLUDE_PARENTS_RX = re.compile(
    r"\b(abstract|kwd-group|article-metadata|fig|figure|caption|table|footnote|"
    r"ref-list|backacknowledgements|backreferences|boxed|sidebar)\b",
    re.I,
)


def _txt(x: str | None) -> str:
    return collapse_spaces(x)


def _has_class(el: Tag, *classes: str) -> bool:
    cls = " ".join(el.get("class") or []).lower()
    return any(c.lower() in cls for c in classes)


def _is_h2_section_title(h: Tag) -> bool:
    return (
        isinstance(h, Tag)
        and h.name
        and h.name.lower() == "h2"
        and _has_class(h, "section-title", "js-splitscreen-section-title")
    )


def _is_hx_section_title(h: Tag) -> bool:
    return (
        isinstance(h, Tag)
        and h.name
        and h.name.lower() in ("h2", "h3", "h4")
        and (_has_class(h, "section-title") or _has_class(h, "js-splitscreen-section-title"))
    )


def _is_abstract_h2(h: Tag) -> bool:
    return (
        isinstance(h, Tag)
        and h.name
        and h.name.lower() == "h2"
        and (
            _has_class(h, "abstract-title")
            or bool(re.search(r"\babstract\b", heading_text(h), re.I))
        )
    )


def _next_sibling_heading(start: Tag, names: tuple[str, ...]) -> Tag | None:
    cur = start.next_sibling
    names = tuple(n.lower() for n in names)
    while cur:
        if isinstance(cur, Tag) and cur.name and cur.name.lower() in names:
            return cur
        cur = cur.next_sibling
    return None


def _iter_between(start: Tag, end: Tag | None) -> Iterator[object]:
    cur = start.next_sibling
    while cur and cur is not end:
        yield cur
        cur = cur.next_sibling


def _collect_paragraphs_between(a: Tag, b: Tag | None) -> list[str]:
    """Lightweight collector: <p> and list <li> text between two sibling anchors."""
    out: list[str] = []
    for node in _iter_between(a, b):
        if not isinstance(node, Tag):
            continue
        if node.name.lower() == "p":
            t = _txt(node.get_text(" ", strip=True))
            if t:
                out.append(t)
        elif node.name.lower() in ("ul", "ol"):
            for li in node.find_all("li", recursive=False):
                t = _txt(li.get_text(" ", strip=True))
                if t:
                    out.append(t)
    return out


# -------------------------- Abstract --------------------------
def _extract_abstract(soup: BeautifulSoup) -> str | None:
    # (A) Explicit abstract container near <h2 class="abstract-title">Abstract</h2>
    for host in soup.select("section.abstract, div.abstract"):
        paras = [p.get_text(" ", strip=True) for p in host.find_all("p")]
        paras = [_txt(p) for p in paras if p]
        if paras:
            return " ".join(paras)
    # (B) Fallback: paragraphs after an abstract H2 up to next H2
    head = soup.find(_is_abstract_h2)
    if head:
        nxt = _next_sibling_heading(head, ("h2",))
        paras = _collect_paragraphs_between(head, nxt)
        if paras:
            return " ".join(paras)
    return None


# -------------------------- Keywords --------------------------
def _extract_keywords(soup: BeautifulSoup) -> list[str]:
    # OUP exposes keywords under .kwd-group with <a class="kwd-part|kwd-main"> (sometimes <span>)
    items: list[str] = []
    for a in soup.select(
        ".kwd-group a.kwd-part, .kwd-group span.kwd-part, "
        ".kwd-group a.kwd-main, .kwd-group span.kwd-main"
    ):
        t = _txt(a.get_text(" ", strip=True))
        if t:
            items.append(t)
    # Fallback: inline "Keywords:" text
    if not items:
        el = soup.find(string=re.compile(r"^\s*Keywords?\s*:", re.I))
        if isinstance(el, str):
            text = re.sub(r"^\s*Keywords?\s*:\s*", "", el, flags=re.I)
            parts = [x.strip() for x in re.split(r"[;,/]|[\r\n]+", text) if x.strip()]
            items.extend(parts)
    items = [x for x in items if x and len(x) > 1]
    return dedupe_keep_order(items)


# -------------------------- Headless lead-in (no H2 "Introduction") --------------------------
def _first_content_h2(soup: BeautifulSoup) -> Tag | None:
    for h in soup.find_all("h2"):
        if _is_h2_section_title(h) and not re.search(r"\babstract\b", heading_text(h), re.I):
            return h
    return None


def _article_root(soup: BeautifulSoup) -> Tag:
    # Typical wrapper for OUP/Silverchair full text
    return soup.select_one("[data-widgetname='ArticleFulltext']") or soup


def _extract_headless_leadin(soup: BeautifulSoup) -> list[str]:
    """
    Collect body paragraphs that appear after the Abstract and before the first H2 section-title.
    Excludes figure/table/caption/metadata regions.
    """
    root = _article_root(soup)
    first_h2 = _first_content_h2(soup)
    seen_abstract = False
    leadin: list[str] = []
    # Mark abstract block nodes so we know when we've passed it
    abstract_host = soup.select_one("section.abstract, div.abstract")
    abstract_h2 = soup.find(_is_abstract_h2)
    # Iterate DOM in document order inside the article root
    for el in root.descendants:
        if not isinstance(el, Tag):
            continue
        # Have we entered/seen the abstract region?
        if el is abstract_host or el is abstract_h2:
            seen_abstract = True
            continue
        # Stop at the first H2 section heading
        if first_h2 is not None and el is first_h2:
            break
        # Only collect once we're past abstract
        if not seen_abstract:
            continue
        # We want narrative body paragraphs, typically <p class="chapter-para">
        if el.name and el.name.lower() == "p":
            # Skip if inside excluded containers (figures, captions, footnotes, etc.)
            if el.find_parent(["figure", "figcaption", "table", "thead", "tbody"]):
                continue
            if el.find_parent(class_=_EXCLUDE_PARENTS_RX):
                continue
            t = _txt(el.get_text(" ", strip=True))
            # Avoid very short junk lines
            if t and len(t) > 40:
                leadin.append(t)
    # de-dup but preserve order
    uniq, seen = [], set()
    for p in leadin:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


# -------------------------- Sections (H2 with optional H3/H4 children) --------------------------
def _extract_sections(soup: BeautifulSoup) -> list[dict[str, object]]:
    """
    Oxford Academic body structure is typically flat headings:
      <h2 class="section-title ...">Materials and Methods</h2>
      <h3 class="section-title ...">Subhead</h3>
      <p class="chapter-para">...</p>
      ...
    We gather H2 sections and nest immediate H3/H4 blocks as children.
    Also merges any headless lead-in paragraphs into the 'Introduction' section if present,
    else creates a synthetic 'Introduction' block at the top.
    """
    # Lead-in paragraphs (if any)
    leadin_paras = _extract_headless_leadin(soup)
    # All H2 that represent real content sections (exclude abstract & backmatter)
    h2s = [h for h in soup.find_all("h2") if _is_h2_section_title(h)]
    h2s = [h for h in h2s if not re.search(r"\babstract\b", heading_text(h), re.I)]
    out: list[dict[str, object]] = []
    for i, h2 in enumerate(h2s):
        title = heading_text(h2)
        if not title or _NONCONTENT_RX.search(title):
            continue
        h2_end = h2s[i + 1] if i + 1 < len(h2s) else None
        # Find immediate H3/H4 children between this H2 and the next H2
        child_heads: list[Tag] = []
        for node in _iter_between(h2, h2_end):
            if (
                isinstance(node, Tag)
                and node.name
                and node.name.lower() in ("h3", "h4")
                and _is_hx_section_title(node)
            ):
                child_heads.append(node)
        # Top-level paragraphs BEFORE the first child, or entire block if no children
        first_child = child_heads[0] if child_heads else None
        parent_paras = _collect_paragraphs_between(h2, first_child or h2_end)
        # Children with their paragraphs (until next child or end)
        children: list[dict[str, object]] = []
        for j, ch in enumerate(child_heads):
            ch_title = heading_text(ch)
            if not ch_title or _NONCONTENT_RX.search(ch_title):
                continue
            ch_end = child_heads[j + 1] if j + 1 < len(child_heads) else h2_end
            ch_paras = _collect_paragraphs_between(ch, ch_end)
            if ch_paras:
                children.append({"title": ch_title, "paragraphs": ch_paras})
        sec: dict[str, object] = {"title": title}
        if parent_paras:
            sec["paragraphs"] = parent_paras
        if children:
            sec["children"] = children
        if sec.get("paragraphs") or sec.get("children"):
            out.append(sec)
    # ----- Merge or create Introduction from headless lead-in -----
    if leadin_paras:
        intro_idx = next(
            (
                i
                for i, n in enumerate(out)
                if isinstance(n.get("title"), str)
                and cast(str, n.get("title")).strip().lower() == "introduction"
            ),
            None,
        )
        if intro_idx is not None:
            prev = cast(list[str], out[intro_idx].get("paragraphs") or [])
            out[intro_idx]["paragraphs"] = dedupe_keep_order(leadin_paras + prev)
        else:
            out.insert(0, {"title": "Introduction", "paragraphs": leadin_paras})
    return dedupe_section_nodes(out)


# -------------------------- References --------------------------
def _strip_ref_noise(tag: Tag) -> None:
    """Remove link toolboxes / extras so raw text reads clean."""
    for sel in [
        ".citation-links",
        ".crossref-doi",
        ".adsDoiReference",
        ".xslopenurl",
        ".worldcat-reference-ref-link",
        ".inst-open-url-holders",
    ]:
        for t in tag.select(sel):
            t.decompose()


def _extract_doi_from(tag: Tag) -> str | None:
    # Prefer DOI anchors
    for a in tag.select("a.link-doi, a[href*='doi.org/']"):
        href = a.get("href") or ""
        text = _txt(a.get_text(" ", strip=True))
        for cand in (text, href):
            m = DOI_RE.search(cand or "")
            if m:
                return m.group(0)
    # Fallback: regex anywhere in the tag text
    m = DOI_RE.search(tag.get_text(" ", strip=True))
    return m.group(0) if m else None


def _extract_pmid_from(tag: Tag) -> str | None:
    for a in tag.select("a[href*='ncbi.nlm.nih.gov/pubmed/'], a.link-pub-id"):
        href = a.get("href") or ""
        m = re.search(r"/pubmed/(\d+)", href)
        if m:
            return m.group(1)
    return None


def parse_oup(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Extract references from Oxford Academic pages.
    Supports:
      • Split-view blocks used by OUP/Silverchair:
        <h2 class="backreferences-title">Literature Cited</h2>
        <div class="ref-list js-splitview-ref-list">
           <div class="js-splitview-ref-item">
             <div class="ref-content"><div class="mixed-citation"> ... </div></div>
           </div>
      • Traditional <ol/ul class="references"><li>...</li></ol> structures.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: list[dict[str, object]] = []
    # Preferred: split-view style
    ref_nodes = soup.select(".ref-list .ref-content")
    if not ref_nodes:
        ref_nodes = soup.select(".ref-list .mixed-citation, .ref-list .ref")
    for node in ref_nodes:
        if not isinstance(node, Tag):
            continue
        _strip_ref_noise(node)
        raw = _txt(node.get_text(" ", strip=True))
        if not raw:
            continue
        ref_base: dict[str, str] = {"raw": raw}
        doi = _extract_doi_from(node)
        if doi:
            ref_base["doi"] = doi
        pmid = _extract_pmid_from(node)
        if pmid:
            ref_base["pmid"] = pmid
        y_el = node.find(class_=re.compile(r"\byear\b", re.I))
        if y_el:
            y_txt = _txt(y_el.get_text(" ", strip=True))
            m = YEAR_RE.search(y_txt) if y_txt else None
            if m:
                ref_base["year"] = m.group(0)
        out.append(augment_from_raw(ref_base))

    # Fallback: list-based selectors
    if not out:
        selectors = [
            "ol.references li",
            "ul.references li",
            "section#references li",
            "section.references li",
            "li[id^='ref']",
            "li[id^='B']",
            "li[id^='R']",
        ]
        for sel in selectors:
            items = soup.select(sel)
            for li in items:
                if not li.get_text(strip=True):
                    continue
                li_base = extract_from_li(li)  # type: dict[str, str]
                out.append(augment_from_raw(li_base))
            if out:
                break
    return out


# -------------------------- public entry (meta/sections) --------------------------
def extract_oup_meta(_url: str, dom_html: str) -> dict[str, object]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abstract = _extract_abstract(soup)
    keywords = _extract_keywords(soup)
    sections = _extract_sections(soup)
    return {"abstract": abstract, "keywords": keywords, "sections": sections}


# -------------------------- registrations --------------------------
# Meta
register_meta(r"(?:^|\.)academic\.oup\.com$", extract_oup_meta, where="host", name="OUP meta")
register_meta(r"oup\.com/", extract_oup_meta, where="url", name="OUP meta (path)")
# References
register(r"(?:^|\.)academic\.oup\.com$", parse_oup, where="host", name="OUP references")
register(r"oup\.com/", parse_oup, where="url", name="OUP references (path)")
