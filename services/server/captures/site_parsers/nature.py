# services/server/captures/site_parsers/nature.py
from __future__ import annotations

"""
Nature site parser: robust abstract/keywords/sections extraction + references.

Public API:
- extract_nature_meta(url, dom_html) -> dict[str, object]
- parse_nature(url, dom_html) -> list[dict[str, object]]

This module registers itself for both host and common proxy patterns.
"""

import re
from urllib.parse import parse_qs, unquote, urlparse

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

# DOI detector (Crossref-ish heuristic)
DOI_RX = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)


def _txt(x: str | None) -> str:
    return collapse_spaces(x)


def _is_figure_descendant(node: Tag) -> bool:
    """True if the node sits inside a figure or a figure-like container."""
    return bool(
        node.find_parent(["figure", "figcaption"]) is not None
        or node.find_parent(class_=_FIGLIKE_CLASS_RX) is not None
    )


def _clean_para_text(s: str) -> str:
    # Filter out trivial “Source data / View figure …” crumbs; keep real content.
    if not s:
        return ""
    stripped = s.strip()
    if re.fullmatch(r"(source data|full size image|open in figure viewer)", stripped, re.I):
        return ""
    return stripped


def _normalize_doi(s: str | None) -> str | None:
    if not s:
        return None
    val = unquote(s).strip()
    # Trim common prefixes and trailing punctuation
    val = re.sub(r"^(?:doi:|https?://(?:dx\.)?doi\.org/)", "", val, flags=re.I)
    val = val.strip().rstrip(" .;,")
    # DOIs are case-insensitive; normalize to lower for consistency
    return val.lower() if val else None


def _extract_doi_from_anchor(a: Tag) -> str | None:
    """
    Try multiple places a DOI might hide:
      - data-track-label / item id / title attributes
      - href query param ?doi=...
      - anywhere in href path (covers /doi/10.x.y and proxied doi-org hosts)
      - visible text (rare)
    """
    # 1) data attributes or title
    for attr in ("data-track-label", "data-track-item_id", "title"):
        v = a.get(attr)
        if v:
            m = DOI_RX.search(unquote(v))
            if m:
                return _normalize_doi(m.group(0))

    # 2) href-based checks
    href = a.get("href") or ""
    if href:
        href_dec = unquote(href)
        parsed = urlparse(href_dec)

        # 2a) doi query parameter (?doi=...)
        qs = parse_qs(parsed.query or "")
        if "doi" in qs and qs["doi"]:
            m = DOI_RX.search(unquote(qs["doi"][0]))
            if m:
                return _normalize_doi(m.group(0))

        # 2b) anywhere in the href
        m = DOI_RX.search(href_dec)
        if m:
            return _normalize_doi(m.group(0))

    # 3) text content as absolute last resort
    t = a.get_text(" ", strip=True)
    if t:
        m = DOI_RX.search(t)
        if m:
            return _normalize_doi(m.group(0))

    return None


def _extract_doi_from_li(li: Tag) -> str | None:
    """
    Prefer 'Article' links first (usually the publisher), then anything else.
    If nothing found in anchors, fall back to scanning the whole <li> text.
    """
    # Prefer anchors that look like "Article"
    candidates: list[Tag] = []
    for a in li.find_all("a"):
        # Weight article-like links to the front
        action = (a.get("data-track-action") or "").lower()
        label = (a.get("data-track-label") or "").lower()
        text = (a.get_text(strip=True) or "").lower()
        if "article" in (text + " " + action) or label.startswith("10."):
            candidates.insert(0, a)
        else:
            candidates.append(a)

    seen: set[str] = set()
    for a in candidates:
        doi = _extract_doi_from_anchor(a)
        if doi and doi not in seen:
            return doi

    # Fall back to scanning the entire list item text
    li_text = li.get_text(" ", strip=True)
    m = DOI_RX.search(li_text)
    if m:
        return _normalize_doi(m.group(0))
    return None


# -------------------------- Abstract --------------------------
def _extract_abstract(soup: BeautifulSoup) -> str | None:
    # Canonical Nature markup variants
    for sec in soup.select(
        "section#Abs1, section[aria-labelledby='Abs1'], section#abstract, "
        "section[aria-labelledby='abstract']"
    ):
        host = sec.select_one(".c-article-section__content") or sec
        paras: list[str] = []
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
        "ul.c-article-subject-list a, "
        "a[data-test='subject-badge'], "
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
            for ptxt in collect_paragraphs_subtree(host):
                text = _clean_para_text(ptxt)
                if text:
                    paras.append(_txt(text))
        node: dict[str, object] = {"title": title, "paragraphs": paras}
        if node.get("paragraphs"):
            out.append(node)
    return dedupe_section_nodes(out)


# -------------------------- References --------------------------
def _reference_items(soup: BeautifulSoup) -> list[Tag]:
    """
    Find reference <li> nodes across Nature's many variants, including the
    right-hand "reading companion" sidebar.
    Order selectors from most-specific to least to reduce false positives.
    """
    selectors = [
        # Reading companion (sidebar)
        "ol.c-reading-companion__references-list > li",
        "li.c-reading-companion__reference-item",
        # Newer magazine layout
        "div[data-container-section='references'] ol.c-article-references > li",
        "ol.c-article-references > li",
        "li.c-article-references__item",
        # Classic Nature markup
        "ol.c-article-references__list > li",
        "section#references li, section.c-article-references li",
        # Fallback data-test hook seen on some articles
        "li[data-test='reference']",
    ]
    seen_ids: set[int] = set()
    items: list[Tag] = []
    for sel in selectors:
        for li in soup.select(sel):
            if not isinstance(li, Tag):
                continue
            key = id(li)
            if key in seen_ids:
                continue
            # Heuristic guard: require some text content
            if not li.get_text(strip=True):
                continue
            seen_ids.add(key)
            items.append(li)
        # If we matched a strong selector set, stop early
        if items and sel in (
            "ol.c-reading-companion__references-list > li",
            "div[data-container-section='references'] ol.c-article-references > li",
            "ol.c-article-references > li",
            "ol.c-article-references__list > li",
        ):
            break
    return items


def parse_nature(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Extract references from Nature pages, including Magazine and Reading Companion variants.
    Adds normalized DOI fields when available.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: list[dict[str, object]] = []
    items = _reference_items(soup)
    for li in items:
        # Strip the outbound link buttons row if present (prevents noise)
        for extra in li.select(".c-article-references__links"):
            extra.decompose()
        if not li.get_text(strip=True):
            continue
        base = extract_from_li(li)
        rec = augment_from_raw(base)

        # --- DOI harvesting ---
        doi = _extract_doi_from_li(li)
        if doi:
            # Only set if absent to avoid clobbering an upstream extractor
            if not rec.get("doi"):
                rec["doi"] = doi
            # Friendly, canonical DOI URL
            rec.setdefault("links", {})
            rec["links"]["doi"] = f"https://doi.org/{rec['doi']}"
        out.append(rec)
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
# Proxy-friendly (e.g., www-nature-com.ezproxy.*, or nature-com inside proxied URLs)
register_meta(r"nature[-\.]com", extract_nature_meta, where="url", name="Nature meta (proxy)")

# References
register(r"(?:^|\.)nature\.com$", parse_nature, where="host", name="Nature references")
register(r"nature\.com/", parse_nature, where="url", name="Nature references (path)")
# Proxy-friendly (e.g., www-nature-com.ezproxy.*)
register(r"nature[-\.]com", parse_nature, where="url", name="Nature references (proxy)")
