# services/server/captures/site_parsers/nature.py
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import (
    augment_from_raw,
    collapse_spaces,
    collect_paragraphs_subtree,
    dedupe_keep_order,
    dedupe_section_nodes,
    extract_from_li,
    heading_text,
)

# -------------------------- small helpers --------------------------
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg|author information|author contributions?|funding|ethics|"
    r"competing interests?|data availability)\b",
    re.I,
)
# Anything figure-like we should ignore when pulling paragraphs
_FIGLIKE_CLASS_RX = re.compile(r"\bc-article-section__figure\b", re.I)


def _txt(x: str | None) -> str:
    return collapse_spaces(x)


def _is_figure_descendant(node: Tag) -> bool:
    # Skip paragraphs that live inside figures/figcaptions or figure containers
    return (
        node.find_parent(["figure", "figcaption"]) is not None
        or node.find_parent(class_=_FIGLIKE_CLASS_RX) is not None
    )


def _clean_para_text(s: str) -> str:
    # Filter out trivial "Source data" / UI cruft lines, keep real content
    if not s:
        return ""
    stripped = s.strip()
    if re.fullmatch(r"(source data|full size image|open in figure viewer)", stripped, re.I):
        return ""
    return stripped


# -------------------------- Abstract --------------------------
def _extract_abstract(soup: BeautifulSoup) -> str | None:
    # Canonical Nature markup variants
    for sec in soup.select(
        "section#Abs1, section[aria-labelledby='Abs1'], section#abstract, "
        "section[aria-labelledby='abstract']"
    ):
        host = sec.select_one(".c-article-section__content") or sec
        paras = []
        for p in host.find_all("p"):
            if _is_figure_descendant(p):
                continue
            text = _clean_para_text(p.get_text(" ", strip=True))
            if text:
                paras.append(text)
        if paras:
            return " ".join(paras)
    # Fallback: any c-article-section (section OR div) whose header title == Abstract
    for sec in soup.select("section.c-article-section, div.c-article-section"):
        h = sec.find(["h2", "h3"], class_=re.compile(r"c-article-section__title|js-section-title"))
        if h and re.search(r"^\s*abstract\s*$", heading_text(h), re.I):
            host = sec.select_one(".c-article-section__content") or sec
            paras = []
            for p in host.find_all("p"):
                if _is_figure_descendant(p):
                    continue
                text = _clean_para_text(p.get_text(" ", strip=True))
                if text:
                    paras.append(text)
            if paras:
                return " ".join(paras)
    return None


# -------------------------- Keywords (subjects) --------------------------
def _extract_keywords(soup: BeautifulSoup) -> list[str]:
    items: list[str] = []
    # Current Nature subject list variants
    for a in soup.select(
        "ul.c-article-subject-list a, "  # generic subject list
        "a[data-test='subject-badge'], "  # newer badge chips
        ".c-article-subjects__list a, .c-article-subjects__link"
    ):
        t = _txt(a.get_text(" ", strip=True))
        if t:
            items.append(t)
    # Fallback: "Keywords:" inline text
    if not items:
        p = soup.find(string=re.compile(r"^\s*Keywords?\s*:", re.I))
        if isinstance(p, str):
            text = re.sub(r"^\s*Keywords?\s*:\s*", "", p, flags=re.I)
            parts = [x.strip() for x in re.split(r"[;,/]|[\r\n]+", text) if x.strip()]
            items.extend(parts)
    items = [x for x in items if x and len(x) > 1]
    return dedupe_keep_order(items)


# -------------------------- Sections --------------------------
def _extract_sections(soup: BeautifulSoup) -> list[dict[str, object]]:
    """
    Nature fulltext typically uses:
      <section or div class="c-article-section" id="...">
        <h2 class="c-article-section__title">...</h2>
        <div class="c-article-section__content"> ... <p>...</p> ... </div>
      </section or div>
    This handles both <section> and <div> containers (Nature sometimes uses <div>).
    """
    out: list[dict[str, object]] = []
    # Support both tags to cover variants
    for sec in soup.select("section.c-article-section, div.c-article-section"):
        h = sec.find(["h2", "h3"], class_=re.compile(r"c-article-section__title|js-section-title"))
        title = heading_text(h) if h else ""
        if not title:
            continue
        if re.search(r"^\s*abstract\s*$", title, re.I) or _NONCONTENT_RX.search(title):
            continue
        host = sec.select_one(".c-article-section__content") or sec
        # Collect real text paragraphs while ignoring figure/caption areas
        paras: list[str] = []
        for p in host.find_all("p"):
            if _is_figure_descendant(p):
                continue
            text = _clean_para_text(p.get_text(" ", strip=True))
            if text:
                paras.append(_txt(text))
        # As a last resort, pull paragraph-like blocks from the subtree (still ignore figures)
        if not paras:
            for p in collect_paragraphs_subtree(host):
                text = _clean_para_text(p)
                if text:
                    paras.append(_txt(text))
        node: dict[str, object] = {"title": title, "paragraphs": paras}
        if node.get("paragraphs"):
            out.append(node)
    return dedupe_section_nodes(out)


# -------------------------- References --------------------------
def _reference_items(soup: BeautifulSoup) -> list[Tag]:
    """
    Find reference <li> nodes across Nature's many variants.
    Order selectors from most-specific to least to reduce false positives.
    """
    selectors = [
        # Newer magazine layout (your snippet)
        "div[data-container-section='references'] ol.c-article-references > li",
        "ol.c-article-references > li",
        "li.c-article-references__item",
        # Classic Nature markup
        "ol.c-article-references__list > li",
        "section#references li, section.c-article-references li",
        # Fallback data-test hook seen on some articles
        "li[data-test='reference']",
    ]
    seen_ids = set()
    items: list[Tag] = []
    for sel in selectors:
        for li in soup.select(sel):
            # Only accept list items that actually contain reference text
            if not isinstance(li, Tag):
                continue
            key = id(li)
            if key in seen_ids:
                continue
            # Heuristic guard: require a p.c-article-references__text OR some text content
            has_text_p = li.select_one("p.c-article-references__text") is not None
            if not has_text_p and not li.get_text(strip=True):
                continue
            seen_ids.add(key)
            items.append(li)
        if items and sel in (
            "div[data-container-section='references'] ol.c-article-references > li",
            "ol.c-article-references > li",
            "ol.c-article-references__list > li",
        ):
            break
    return items


def parse_nature(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Extract references from Nature pages, including the Magazine layout variant.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: list[dict[str, object]] = []
    items = _reference_items(soup)
    for li in items:
        # Strip the row of outbound link buttons so they don't pollute parsing
        for extra in li.select(".c-article-references__links"):
            extra.decompose()
        if not li.get_text(strip=True):
            continue
        base = extract_from_li(li)
        out.append(augment_from_raw(base))
    return out


# -------------------------- public entry (meta/sections) --------------------------
def extract_nature_meta(_url: str, dom_html: str) -> dict[str, object]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abstract = _extract_abstract(soup)
    keywords = _extract_keywords(soup)
    sections = _extract_sections(soup)
    return {"abstract": abstract, "keywords": keywords, "sections": sections}


# -------------------------- registrations --------------------------
# Meta
register_meta(r"(?:^|\.)nature\.com$", extract_nature_meta, where="host", name="Nature meta")
register_meta(r"nature\.com/", extract_nature_meta, where="url", name="Nature meta (path)")
# References
register(r"(?:^|\.)nature\.com$", parse_nature, where="host", name="Nature references")
register(r"nature\.com/", parse_nature, where="url", name="Nature references (path)")
