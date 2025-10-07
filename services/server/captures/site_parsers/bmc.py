# services/server/captures/site_parsers/bmc.py
from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs, unquote

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
# BMC uses Springer Nature's "c-article-*" design system (very similar to Nature).
_NONCONTENT_RX = re.compile(
    r"\b("
    r"references?|acknowledg|author information|author contributions?|"
    r"funding|ethics|competing interests?|data availability|supplementary"
    r")\b",
    re.I,
)
# Ignore figure/caption content when collecting paragraphs
_FIGLIKE_CLASS_RX = re.compile(r"\bc-article-section__figure\b", re.I)

# DOI detector (Crossref-ish heuristic)
DOI_RX = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)


def _txt(x: str | None) -> str:
    return collapse_spaces(x)


def _is_figure_descendant(node: Tag) -> bool:
    # Skip paragraphs sitting inside figures/figcaptions or their containers
    return (
        node.find_parent(["figure", "figcaption"]) is not None
        or node.find_parent(class_=_FIGLIKE_CLASS_RX) is not None
    )


def _clean_para_text(s: str) -> str:
    if not s:
        return ""
    stripped = s.strip()
    # Remove tiny UI crumbs that sometimes appear in figure areas
    if re.fullmatch(r"(source data|full size image|open in figure viewer)", stripped, re.I):
        return ""
    return stripped


def _normalize_doi(s: str | None) -> str | None:
    if not s:
        return None
    val = unquote(s).strip()
    # Trim prefixes and trailing punctuation
    val = re.sub(r"^(?:doi:|https?://(?:dx\.)?doi\.org/)", "", val, flags=re.I)
    val = val.strip().rstrip(" .;,")
    return val.lower() if val else None


def _extract_doi_from_anchor(a: Tag) -> str | None:
    """
    Try multiple places a DOI might hide:
      - data-track-label / title attributes
      - href query param ?doi=...
      - anywhere in href path (covers /doi/10.x.y and proxied doi-org hosts)
      - visible text (rare)
    """
    # 1) attributes
    for attr in ("data-track-label", "title"):
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

        # 2a) doi query parameter
        qs = parse_qs(parsed.query or "")
        if "doi" in qs and qs["doi"]:
            m = DOI_RX.search(unquote(qs["doi"][0]))
            if m:
                return _normalize_doi(m.group(0))

        # 2b) anywhere in href
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
    Prefer "Article" links first (usually the publisher), then anything else.
    If nothing found in anchors, fall back to scanning the whole <li> text.
    """
    candidates: list[Tag] = []
    for a in li.find_all("a"):
        label = (a.get("data-track-label") or "").lower()
        txt = (a.get_text(strip=True) or "").lower()
        if "article" in (txt + " " + label) or label.startswith("10."):
            candidates.insert(0, a)
        else:
            candidates.append(a)
    for a in candidates:
        doi = _extract_doi_from_anchor(a)
        if doi:
            return doi
    m = DOI_RX.search(li.get_text(" ", strip=True))
    return _normalize_doi(m.group(0)) if m else None


# -------------------------- Abstract --------------------------
def _extract_abstract(soup: BeautifulSoup) -> str | None:
    # Canonical BMC/SpringerOpen abstract hosts
    for sec in soup.select(
        "section#Abs1, section[aria-labelledby='Abs1'], "
        "section#abstract, section[aria-labelledby='abstract']"
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

    # Fallback: any c-article-section titled "Abstract"
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
    # Typical BMC subjects list
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
            items.extend([x.strip() for x in re.split(r"[;,/]|\r?\n", text) if x.strip()])
    items = [x for x in items if x and len(x) > 1]
    return dedupe_keep_order(items)


# -------------------------- Sections --------------------------
def _extract_sections(soup: BeautifulSoup) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for sec in soup.select("section.c-article-section, div.c-article-section"):
        h = sec.find(["h2", "h3"], class_=re.compile(r"c-article-section__title|js-section-title"))
        title = heading_text(h) if h else ""
        if not title:
            continue
        if re.search(r"^\s*abstract\s*$", title, re.I) or _NONCONTENT_RX.search(title):
            continue
        host = sec.select_one(".c-article-section__content") or sec
        paras: list[str] = []
        for p in host.find_all("p"):
            if _is_figure_descendant(p):
                continue
            text = _clean_para_text(p.get_text(" ", strip=True))
            if text:
                paras.append(_txt(text))
        # As a backstop, pull paragraph-like blocks from the subtree (still ignore fig-like)
        if not paras:
            for t in collect_paragraphs_subtree(host):
                ct = _clean_para_text(t)
                if ct:
                    paras.append(_txt(ct))
        node: dict[str, object] = {"title": title, "paragraphs": paras}
        if node.get("paragraphs"):
            out.append(node)
    return dedupe_section_nodes(out)


# -------------------------- References --------------------------
def _reference_items_bmc(soup: BeautifulSoup) -> list[Tag]:
    selectors = [
        # Typical BMC references container
        "div[data-container-section='references'] ol.c-article-references > li",
        "ol.c-article-references__list > li",
        "ol.c-article-references > li",
        # Safe fallbacks
        "section#references li, section.c-article-references li",
        "li[data-test='reference']",
    ]
    items: list[Tag] = []
    seen = set()
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
        # stop early if we matched a strong selector
        if items and sel in (
            "div[data-container-section='references'] ol.c-article-references > li",
            "ol.c-article-references__list > li",
            "ol.c-article-references > li",
        ):
            break
    return items


def parse_bmc(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Extract references from BMC pages (SpringerOpen layout).
    Adds normalized DOI fields when available.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: list[dict[str, object]] = []
    items = _reference_items_bmc(soup)
    for li in items:
        # Remove the outbound link toolbar row if present
        for extra in li.select(".c-article-references__links"):
            extra.decompose()
        if not li.get_text(strip=True):
            continue
        base = extract_from_li(li)
        rec = augment_from_raw(base)
        doi = _extract_doi_from_li(li)
        if doi:
            if not rec.get("doi"):
                rec["doi"] = doi
            rec.setdefault("links", {})
            rec["links"]["doi"] = f"https://doi.org/{rec['doi']}"
        out.append(rec)
    return out


# -------------------------- public entry (meta/sections) --------------------------
def extract_bmc_meta(_url: str, dom_html: str) -> dict[str, object]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abstract = _extract_abstract(soup)
    keywords = _extract_keywords(soup)
    sections = _extract_sections(soup)
    return {"abstract": abstract, "keywords": keywords, "sections": sections}


# -------------------------- registrations --------------------------
# Host pattern covers e.g. bmcbioinformatics.biomedcentral.com, bmcresnotes.biomedcentral.com, etc.
register_meta(r"(?:^|\.)biomedcentral\.com$", extract_bmc_meta, where="host", name="BMC meta")
register_meta(r"biomedcentral[-\.]", extract_bmc_meta, where="url", name="BMC meta (proxy)")
register(r"(?:^|\.)biomedcentral\.com$", parse_bmc, where="host", name="BMC references")
register(r"biomedcentral[-\.]", parse_bmc, where="url", name="BMC references (proxy)")
