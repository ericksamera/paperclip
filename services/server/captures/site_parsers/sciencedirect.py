# services/server/captures/site_parsers/sciencedirect.py
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
ScienceDirect parser
--------------------

Goals:
- Robust extraction of abstract, keywords and section text across classic and
  newer Elsevier/ScienceDirect templates.
- Reference harvesting with DOI normalization (from hrefs, data attrs or text).
- Defensive against figure/caption/graphical-abstract noise.
- Black/ruff friendly.

Public API:
- extract_sciencedirect_meta(url, dom_html) -> dict[str, object]
- parse_sciencedirect(url, dom_html) -> list[dict[str, object]]

This module registers itself for host, path, and proxy-like patterns.
"""

# --------------------------------------------------------------------------------------
# Patterns / heuristics
# --------------------------------------------------------------------------------------

# Sections we generally consider "non-content" for the main text body
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg(e)?ments?|author (information|contributions?)|"
    r"funding|ethics|conflict of interest|competing interests?|data availability|"
    r"supplementary (data|material)|appendix|abbreviations)\b",
    re.I,
)

# SD often has "Graphical abstract" blocks; exclude those when extracting the abstract
_ABSTRACT_EXCLUDE_RX = re.compile(r"\b(graphical|visual)\s+abstract\b", re.I)

# DOI detector (Crossref-ish heuristic)
DOI_RX = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)


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
    Try multiple places a DOI might hide in ScienceDirect:
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
    Prefer anchors that look like primary 'Article' links or which carry
    DOI-ish labels, then fall back to scanning the whole item text.
    """
    candidates: list[Tag] = []
    for a in li.find_all("a"):
        text = (a.get_text(strip=True) or "").lower()
        dlabel = (a.get("data-analytics-link") or "").lower()
        if "https://doi.org" in (a.get("href") or "") or "article" in (
            text + " " + dlabel
        ):
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
    """True if a node sits within a figure/caption/table/aside area."""
    return bool(
        node.find_parent(["figure", "figcaption", "table", "aside"]) is not None
    )


def _clean_para_text(s: str) -> str:
    if not s:
        return ""
    stripped = s.strip()
    # Common UI crumbs in SD content blocks
    if re.fullmatch(r"(download|open|view)\s+(figure|image|table)", stripped, re.I):
        return ""
    return stripped


# --------------------------------------------------------------------------------------
# Abstract / keywords / sections
# --------------------------------------------------------------------------------------
def _extract_abstract(soup: BeautifulSoup) -> str | None:
    """
    ScienceDirect variants seen in the wild:
      - <section class="Abstracts"> ... <div class="abstract author"> <p>...</p>
      - <div id="abs0005"> <p>...</p> (older)
      - <div class="Abstracts"> ... </div>
      - 'Graphical abstract' blocks (ignored)
    Strategy:
      - Look for containers with id/class matching 'abstract'
      - Exclude those whose heading says 'Graphical abstract'
    """
    # 1) Explicit "Abstracts" containers
    for sec in soup.select(
        "section.Abstracts, div.Abstracts, section#abstract, div#abstract"
    ):
        # If there's a visible header and it's a graphical abstract, skip
        head = sec.find(["h2", "h3"])
        if head and _ABSTRACT_EXCLUDE_RX.search(heading_text(head)):
            continue

        host = (
            sec.select_one(".abstract.author, .abstract, .Abstract, .article__abstract")
            or sec
        )
        paras: list[str] = []
        for p in host.find_all("p"):
            if _is_figure_descendant(p):
                continue
            text = _clean_para_text(p.get_text(" ", strip=True))
            if text:
                paras.append(text)
        if paras:
            return " ".join(paras)

    # 2) Any id/class containing "abstract" (coarse fallback)
    for sec in soup.select("[id*='abstract' i], [class*='abstract' i]"):
        head = sec.find(["h2", "h3"])
        if head and _ABSTRACT_EXCLUDE_RX.search(heading_text(head)):
            continue
        paras = []
        for p in sec.find_all("p"):
            if _is_figure_descendant(p):
                continue
            text = _clean_para_text(p.get_text(" ", strip=True))
            if text:
                paras.append(text)
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
      - <div class="keywords"> <span class="keyword">X</span> ...
      - <section ... data-type="author-keywords"> ... <a>Term</a> ...
      - Inline "Keywords:" label near abstract
    """
    out: list[str] = []

    # 1) Canonical keywords blocks
    for a in soup.select(
        ".keywords .keyword, .Keywords .keyword, "
        "section[data-type*='keyword' i] a, section[data-type*='keyword' i] .keyword, "
        "div[class*='keyword' i] a, div[class*='keyword' i] span"
    ):
        t = _txt(a.get_text(" ", strip=True))
        if t:
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
    ScienceDirect body sections usually look like:
      <section id="s0005" class="...">
        <h2>Introduction</h2>
        <div class="..."> <p>...</p> ... </div>
      </section>

    Strategy:
      - Find sections with headings (h2/h3) under <section> or <div>.
      - Skip Abstract (handled separately) and administrative blocks.
    """
    out: list[dict[str, object]] = []

    for sec in soup.select("section, div.Section, div[class*='section' i]"):
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
        # Primary: direct paragraph scan (filter out figure/caption/table/etc.)
        for p in host.find_all("p"):
            if _is_figure_descendant(p):
                continue
            text = _clean_para_text(p.get_text(" ", strip=True))
            if text:
                paras.append(_txt(text))

        # Secondary: subtree collector fallback if we found nothing
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
    Find reference <li> nodes across SD variants:
      - <ol class="reference-list"> <li>...</li> ...
      - <ol class="BibliographyList"> ...
      - <section id="references"> <li>...</li>
    Order selectors from specific to general to reduce false positives.
    """
    selectors = [
        "ol.reference-list > li",
        "ol.ReferenceList > li",
        "ol.BibliographyList > li",
        "section#references li",
        "div#references li",
        # very coarse fallback
        "ol li.reference, ol li.citation",
    ]
    items: list[Tag] = []
    seen: set[int] = set()
    for sel in selectors:
        for li in soup.select(sel):
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
            "ol.reference-list > li",
            "ol.ReferenceList > li",
            "ol.BibliographyList > li",
        ):
            break
    return items


def parse_sciencedirect(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Extract references, adding normalized 'doi' and a friendly DOI link when found.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: list[dict[str, object]] = []
    for li in _reference_items(soup):
        # Strip common link-button rows to reduce noise
        for extra in li.select(".ref-links, .reference-actions, .sv-links"):
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
def extract_sciencedirect_meta(_url: str, dom_html: str) -> dict[str, object]:
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
    r"(?:^|\.)sciencedirect\.com$",
    extract_sciencedirect_meta,
    where="host",
    name="ScienceDirect meta",
)
register_meta(
    r"sciencedirect\.com/",
    extract_sciencedirect_meta,
    where="url",
    name="ScienceDirect meta (path)",
)
register_meta(
    r"sciencedirect[-\.]com",
    extract_sciencedirect_meta,
    where="url",
    name="ScienceDirect meta (proxy)",
)

# References
register(
    r"(?:^|\.)sciencedirect\.com$",
    parse_sciencedirect,
    where="host",
    name="ScienceDirect references",
)
register(
    r"sciencedirect\.com/",
    parse_sciencedirect,
    where="url",
    name="ScienceDirect references (path)",
)
register(
    r"sciencedirect[-\.]com",
    parse_sciencedirect,
    where="url",
    name="ScienceDirect references (proxy)",
)
