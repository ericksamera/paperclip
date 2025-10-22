# services/server/captures/site_parsers/oup.py
from __future__ import annotations

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

"""
Oxford Academic (OUP) parser
----------------------------

Goals
- Robustly extract abstract, keywords, and fulltext section paragraphs across
  classic and modern OUP templates on academic.oup.com.
- Harvest references with DOI normalization from hrefs, data attrs, or text.
- Be defensive against figure/caption/aside noise.
- Black- and ruff-friendly.

Public API
- extract_oup_meta(url, dom_html) -> dict[str, object]
- parse_oup(url, dom_html) -> list[dict[str, object]]

This module registers itself for host + common proxy-like patterns.
"""

# --------------------------------------------------------------------------------------
# Patterns / heuristics
# --------------------------------------------------------------------------------------

# (Crossref-ish) DOI detector
DOI_RX = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)

# Sections we generally treat as non-body content
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg(e)?ments?|author (information|contributions?)|"
    r"funding|ethics|conflict of interest|competing interests?|data availability|"
    r"supplementary (data|material)|appendix|abbreviations)\b",
    re.I,
)


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------
def _txt(x: str | None) -> str:
    return collapse_spaces(x)


def _normalize_doi(s: str | None) -> str | None:
    if not s:
        return None
    val = unquote(s).strip()
    # Trim common prefixes and trailing punctuation
    val = re.sub(r"^(?:doi:|https?://(?:dx\.)?doi\.org/)", "", val, flags=re.I)
    val = val.strip().rstrip(" .;,")
    return val.lower() if val else None


def _extract_doi_from_anchor(a: Tag) -> str | None:
    """
    Try multiple places a DOI might hide in OUP pages:
      - data-doi / data-analytics-* / title attrs
      - href query param (?doi=...) or path (/doi/10.x.y)
      - visible text as last resort
    """
    # 1) data/title attributes
    for attr in ("data-doi", "data-analytics-doi", "data-analytics-link", "title"):
        v = a.get(attr)
        if v:
            m = DOI_RX.search(unquote(v))
            if m:
                return _normalize_doi(m.group(0))

    # 2) href-based
    href = a.get("href") or ""
    if href:
        href_dec = unquote(href)
        parsed = urlparse(href_dec)

        # 2a) explicit ?doi=...
        qs = parse_qs(parsed.query or "")
        if "doi" in qs and qs["doi"]:
            m = DOI_RX.search(unquote(qs["doi"][0]))
            if m:
                return _normalize_doi(m.group(0))

        # 2b) anywhere in the href
        m = DOI_RX.search(href_dec)
        if m:
            return _normalize_doi(m.group(0))

    # 3) text content
    t = a.get_text(" ", strip=True)
    if t:
        m = DOI_RX.search(t)
        if m:
            return _normalize_doi(m.group(0))

    return None


def _extract_doi_from_li(li: Tag) -> str | None:
    """
    Prefer obvious Article/DOI anchors first, then scan all anchors, then the LI text.
    """
    candidates: list[Tag] = []
    for a in li.find_all("a"):
        text = (a.get_text(strip=True) or "").lower()
        if "https://doi.org" in (a.get("href") or "") or "article" in text:
            candidates.insert(0, a)
        else:
            candidates.append(a)

    for a in candidates:
        doi = _extract_doi_from_anchor(a)
        if doi:
            return doi

    m = DOI_RX.search(li.get_text(" ", strip=True))
    if m:
        return _normalize_doi(m.group(0))
    return None


def _is_figure_descendant(node: Tag) -> bool:
    """True if a node sits within a figure/caption/table/aside/footnotes area."""
    return bool(
        node.find_parent(["figure", "figcaption", "table", "aside", "footer"])
        is not None
    )


def _clean_para_text(s: str) -> str:
    if not s:
        return ""
    stripped = s.strip()
    # Common UI crumbs in content blocks
    if re.fullmatch(r"(download|open|view)\s+(figure|image|table)", stripped, re.I):
        return ""
    return stripped


# --------------------------------------------------------------------------------------
# Abstract / keywords / sections
# --------------------------------------------------------------------------------------
def _extract_abstract(soup: BeautifulSoup) -> str | None:
    """
    OUP variants seen in the wild:
      - <section id="abstract"> ... <p>...</p>
      - <div class="abstract"> ... <p>...</p>
      - Heading 'Abstract' followed by paragraphs
    Strategy:
      - Prefer explicit abstract hosts with id/class hints.
      - Fallback: a heading titled 'Abstract' and paragraphs until next heading.
    """
    # 1) Structured abstract containers
    for host in soup.select(
        "section#abstract, div#abstract, section[class*='abstract' i], div[class*='abstract' i]"
    ):
        content = host.select_one(".article-section__content") or host
        paras = []
        for p in content.find_all("p"):
            if _is_figure_descendant(p):
                continue
            text = _clean_para_text(p.get_text(" ", strip=True))
            if text:
                paras.append(text)
        if paras:
            return " ".join(paras)

    # 2) Heading-based fallback
    for h in soup.find_all(["h2", "h3", "h4"]):
        title = heading_text(h)
        if re.fullmatch(r"\s*abstract\s*", title or "", re.I):
            paras: list[str] = []
            cur = h.next_sibling
            while cur:
                if isinstance(cur, Tag) and cur.name in {"h2", "h3", "h4"}:
                    break
                if isinstance(cur, Tag):
                    for p in cur.find_all("p"):
                        if _is_figure_descendant(p):
                            continue
                        text = _clean_para_text(p.get_text(" ", strip=True))
                        if text:
                            paras.append(text)
                cur = cur.next_sibling
            if paras:
                return " ".join(paras)

    # 3) Meta description fallback
    md = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if md and md.get("content"):
        content = md["content"].strip()
        if 40 <= len(content) <= 2000:
            return content

    return None


def _extract_keywords(soup: BeautifulSoup) -> list[str]:
    """
    Variants:
      - <section id="keywords"> ... <li>Term</li> ...
      - <div class="kwd-group"> <span class="kwd-text">Term</span> ...
      - Inline 'Keywords:' label near abstract
    """
    out: list[str] = []

    # 1) Canonical keywords blocks
    for host in soup.select(
        "section#keywords, div#keywords, "
        "section[class*='keyword' i], div[class*='keyword' i], "
        "div.kwd-group, div.kwdGroup",
    ):
        for el in host.select("a, li, span, strong"):
            t = _txt(el.get_text(" ", strip=True))
            if t and not re.fullmatch(r"keywords?\s*:?", t, re.I):
                out.append(t)

    # 2) Inline "Keywords:" fallback
    if not out:
        node = soup.find(string=re.compile(r"^\s*Keywords?\s*:\s*", re.I))
        if isinstance(node, str):
            text = re.sub(r"^\s*Keywords?\s*:\s*", "", node, flags=re.I)
            parts = [x.strip() for x in re.split(r"[;,/]|[\r\n]+", text) if x.strip()]
            out.extend(parts)

    out = [x for x in out if x and len(x) > 1]
    return dedupe_keep_order(out)


def _extract_sections(soup: BeautifulSoup) -> list[dict[str, object]]:
    """
    OUP body sections often look like:
      <section id="sec-...">
        <h2>Introduction</h2>
        <div class="..."> <p>...</p> ... </div>
      </section>

    Strategy:
      - Find sections with headings (h2/h3) under <section> or <div>.
      - Skip Abstract (handled separately) and administrative blocks.
      - Collect paragraph-like text, ignoring figure/caption/aside areas.
    """
    out: list[dict[str, object]] = []

    # Prefer the main/article wrapper if present
    wrapper = soup.find("main") or soup.find("article") or soup

    for sec in wrapper.select("section, div.section, div[class*='section' i]"):
        h = sec.find(["h2", "h3"])
        title = heading_text(h) if h else ""
        if not title:
            continue
        if re.search(r"^\s*abstract\s*$", title, re.I) or _NONCONTENT_RX.search(title):
            continue

        # Prefer a content host if present
        host = (
            sec.select_one(
                "div[class*='content' i], div[class*='body' i], div.section-content"
            )
            or sec
        )

        paras: list[str] = []
        for p in host.find_all("p"):
            if _is_figure_descendant(p):
                continue
            text = _clean_para_text(p.get_text(" ", strip=True))
            if text:
                paras.append(_txt(text))

        # Fallback: subtree collector if nothing found
        if not paras:
            for ptxt in collect_paragraphs_subtree(host):
                text = _clean_para_text(ptxt)
                if text:
                    paras.append(_txt(text))

        node: dict[str, object] = {"title": title, "paragraphs": paras}
        if node.get("paragraphs"):
            out.append(node)

    return dedupe_section_nodes(out)


# --------------------------------------------------------------------------------------
# References
# --------------------------------------------------------------------------------------
def _reference_items(soup: BeautifulSoup) -> list[Tag]:
    """
    Find reference <li> nodes across OUP variants:
      - <section id="references"> <ol> <li>...</li> ...
      - <div id="References"> ...
      - Sidebar/reading-companion lists
    Order selectors from specific to general.
    """
    selectors = [
        "section#references ol > li",
        "section#references li",
        "div#References ol > li",
        "div#References li",
        "div[data-widget='articleReferences'] li",
        "ol.citation-list > li",
        "ol.references > li",
        "ul.references > li",
        # coarse fallback
        "li[data-ref-id], li[id^='ref-'], li.reference",
    ]
    items: list[Tag] = []
    seen: set[int] = set()
    for sel in selectors:
        hits = soup.select(sel)
        for li in hits:
            if not isinstance(li, Tag):
                continue
            if not li.get_text(strip=True):
                continue
            key = id(li)
            if key in seen:
                continue
            seen.add(key)
            items.append(li)
        if items and sel in (
            "section#references ol > li",
            "div#References ol > li",
            "ol.citation-list > li",
        ):
            break
    return items


def parse_oup(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Extract references, adding normalized 'doi' and a friendly DOI link when found.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: list[dict[str, object]] = []
    for li in _reference_items(soup):
        # Strip obvious link-button rows to reduce noise (class names vary a lot; be conservative)
        for extra in li.select(
            ".ref-links, .reference-actions, .c-article-references__links"
        ):
            extra.decompose()

        base = extract_from_li(li)
        if not base.get("raw"):
            # Guard: skip if the item collapsed to nothing
            continue

        rec = augment_from_raw(base)

        doi = _extract_doi_from_li(li)
        if doi:
            if not rec.get("doi"):
                rec["doi"] = doi
            rec.setdefault("links", {})
            rec["links"]["doi"] = f"https://doi.org/{rec['doi']}"

        out.append(rec)
    return out


# --------------------------------------------------------------------------------------
# Public meta entry
# --------------------------------------------------------------------------------------
def extract_oup_meta(_url: str, dom_html: str) -> dict[str, object]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abstract = _extract_abstract(soup)
    keywords = _extract_keywords(soup)
    sections = _extract_sections(soup)
    return {"abstract": abstract, "keywords": keywords, "sections": sections}


# --------------------------------------------------------------------------------------
# Registrations
# --------------------------------------------------------------------------------------
# Meta
register_meta(
    r"(?:^|\.)academic\.oup\.com$",
    extract_oup_meta,
    where="host",
    name="OUP meta",
)
register_meta(
    r"academic\.oup\.com/",
    extract_oup_meta,
    where="url",
    name="OUP meta (path)",
)
register_meta(
    r"oup[-\.]com",
    extract_oup_meta,
    where="url",
    name="OUP meta (proxy)",
)

# References
register(
    r"(?:^|\.)academic\.oup\.com$",
    parse_oup,
    where="host",
    name="OUP references",
)
register(
    r"academic\.oup\.com/",
    parse_oup,
    where="url",
    name="OUP references (path)",
)
register(
    r"oup[-\.]com",
    parse_oup,
    where="url",
    name="OUP references (proxy)",
)
