# services/server/captures/site_parsers/sciencedirect.py
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import cast

from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import (
    augment_from_raw,
    collapse_spaces,
    collect_paragraphs_subtree,
    collect_sd_paragraphs,
    dedupe_keep_order,
    extract_from_li,
    heading_text,
)

# ======================================================================================
# Helpers
# ======================================================================================
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg|conflict of interest|ethics|funding|data availability|"
    r"author contributions?)\b",
    re.I,
)

# Noise lines commonly embedded in figure/table widgets on SD pages
_HEADLESS_NOISE_RX = re.compile(
    r"(?:download:? (?:full[- ]size|high[- ]res) image|open in new tab|view (?:large|figure))",
    re.I,
)

def _has_direct_heading(sec: Tag, levels: Iterable[str]) -> Tag | None:
    """Return the direct child heading tag (h2/h3/h4) if present."""
    for lvl in levels:
        h = sec.find(lvl, recursive=False)
        if h:
            return h
    return None

def _good_title(h: Tag | None) -> str:
    if not h:
        return ""
    t = heading_text(h)
    # Tiny guard: SD sometimes repeats empty headings for anchors
    return collapse_spaces(t)

def _parse_sd_section(sec: Tag, seen_ids: set[str]) -> dict[str, object] | None:
    sid = (sec.get("id") or "").strip()
    if sid:
        if sid in seen_ids:
            return None
        seen_ids.add(sid)

    h = _has_direct_heading(sec, ("h2", "h3", "h4")) or sec.find(["h2", "h3", "h4"])
    title = _good_title(h)
    if title and _NONCONTENT_RX.search(title):
        return None

    paragraphs = collect_sd_paragraphs(sec)

    children: list[dict[str, object]] = []
    for child_sec in sec.find_all("section", recursive=False):
        child_node = _parse_sd_section(child_sec, seen_ids)
        if child_node and (
            child_node.get("title") or child_node.get("paragraphs") or child_node.get("children")
        ):
            children.append(child_node)

    def key_fn(n: dict[str, object]) -> str:
        title = (n.get("title") or "") if isinstance(n.get("title"), str) else ""
        first = ""
        if isinstance(n.get("paragraphs"), list) and n["paragraphs"]:
            paras = cast(list[str], n["paragraphs"])
            first = paras[0]
        return f"{title}::{first}"

    deduped: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for n in children:
        k = key_fn(n)
        if k not in seen_keys:
            seen_keys.add(k)
            deduped.append(n)

    node: dict[str, object] = {"title": title, "paragraphs": paragraphs}
    if deduped:
        node["children"] = deduped
    return node

def _find_top_sections(soup: BeautifulSoup) -> list[Tag]:
    """
    ScienceDirect wraps the article body in <section id="secXXXX"> blocks.
    We want the highest level that actually exists on the page (usually <h2>),
    and only those <section> nodes where that heading is a direct child.
    """
    all_secs = [s for s in soup.find_all("section") if isinstance(s, Tag)]
    # Determine the minimal heading level present as a direct child anywhere
    has_h2 = any(_has_direct_heading(s, ("h2",)) for s in all_secs)
    has_h3 = any(_has_direct_heading(s, ("h3",)) for s in all_secs)
    levels: tuple[str, ...]
    if has_h2:
        levels = ("h2",)
    elif has_h3:
        levels = ("h3",)
    else:
        levels = ("h4",)
    tops: list[Tag] = []
    for s in all_secs:
        h = _has_direct_heading(s, levels)
        if not h:
            continue
        # Ignore sections that are clearly non-content
        if _NONCONTENT_RX.search(_good_title(h) or ""):
            continue
        tops.append(s)
    # If we accidentally grabbed nested sections (e.g., <section><h2>…</h2><section>…),
    # keep only those that are not inside another top candidate.
    top_set = set(tops)
    really_top: list[Tag] = []
    for s in tops:
        par = s.find_parent("section")
        keep = True
        while par:
            if par in top_set and _has_direct_heading(par, levels):
                keep = False
                break
            par = par.find_parent("section")
        if keep:
            really_top.append(s)
    return really_top

def _extract_sd_sections(soup: BeautifulSoup) -> list[dict[str, object]]:
    """
    Build a clean section tree for SD pages without duplicating children.
    If no titled sections exist (headless variant), synthesize a single 'Introduction'.
    """
    out: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for s in _find_top_sections(soup):
        node = _parse_sd_section(s, seen_ids)
        if not node:
            continue
        # Keep nodes that have either title or some text/children
        if node.get("title") or node.get("paragraphs") or node.get("children"):
            out.append(node)
    if out:
        return out

    # ------- HEADLESS FALLBACK (no <h2>/<h3> titles) -------
    # Many Elsevier/Silverlight builds render the main narrative under <div id="body" class="Body ...">
    host = (
        soup.select_one("div#body.Body")
        or soup.select_one("div.Body#body")
        or soup.select_one("div.Body")
        or soup.select_one("div#body")
    )
    if host:
        # Collect paragraphs across the subtree; drop obvious UI/figure-download lines
        paras = [
            t for t in (collect_paragraphs_subtree(host) or []) if t and not _HEADLESS_NOISE_RX.search(t)
        ]
        # Be conservative: require a few lines so we don't create empty shells
        if paras[:3]:
            return [{"title": "Introduction", "paragraphs": paras}]
    return []

# ======================================================================================
# Meta: abstract, keywords, sections
# ======================================================================================
def _extract_abstract(soup: BeautifulSoup) -> str:
    # A) Explicit abstract containers (div/section with class 'abstract' or id like 'abs0001')
    for host in soup.select(
        "div.abstract, section.abstract, div[id^='abs' i], section[id^='abs' i]"
    ):
        paras = [t for t in collect_paragraphs_subtree(host) if t.strip()]
        if paras:
            return " ".join(paras)
    # B) Heading 'Abstract' → take paragraphs from its nearest container (section/div) subtree
    for h in soup.find_all(["h2", "h3", "h4"]):
        if not h.get_text(strip=True):
            continue
        if re.search(r"^\s*abstract\s*$", h.get_text(" ", strip=True), re.I):
            container = h.find_parent(["section", "div"]) or h.parent
            if container:
                paras = [t for t in collect_paragraphs_subtree(container) if t.strip()]
                if paras:
                    return " ".join(paras)
    # C) Meta tags
    for name in ("dc.description", "dcterms.abstract", "citation_abstract"):
        m = soup.find("meta", attrs={"name": name})
        if m and m.get("content"):
            t = collapse_spaces(m["content"])
            if t:
                return t
    return ""

def _extract_keywords(soup: BeautifulSoup) -> list[str]:
    kws: list[str] = []
    # meta tags first
    for name in ("citation_keywords", "keywords", "dc.subject", "dcterms.subject"):
        for m in soup.find_all("meta", attrs={"name": name}):
            content = collapse_spaces(m.get("content") or "")
            if not content:
                continue
            parts = re.split(r"[;,]\s*", content)
            parts = [p for p in parts if p]
            kws.extend(parts)
    if kws:
        return dedupe_keep_order(kws)
    # On-page keywords blocks (loose heuristics)
    for lab in soup.find_all(["h2", "h3", "h4"]):
        t = collapse_spaces(lab.get_text(" ", strip=True))
        if not re.search(r"\bkeywords\b", t, re.I):
            continue
        box = lab.find_parent("section") or lab.parent
        if not box:
            continue
        items: list[str] = []
        for li in box.find_all("li"):
            txt = collapse_spaces(li.get_text(" ", strip=True))
            if txt and len(txt) > 1:
                items.append(txt)
        if items:
            kws.extend(items)
            break
    return dedupe_keep_order(kws)

def extract_sciencedirect_meta(_url: str, dom_html: str) -> dict[str, object]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abstract = _extract_abstract(soup)
    keywords = _extract_keywords(soup)
    sections = _extract_sd_sections(soup)
    return {"abstract": abstract, "keywords": keywords, "sections": sections}

# ======================================================================================
# References
# ======================================================================================
def parse_sciencedirect(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Extract references from ScienceDirect pages. We keep this intentionally
    permissive because SD markup varies a lot across journals.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: list[dict[str, object]] = []
    selectors = [
        # Common SD markup (ordered list of references)
        "ol.references li",
        "ul.references li",
        # Fallbacks that show up on some journals/collections
        "section.references li",
        "section#references li",
        "li[id^='ref'], li[id^='B'], li[id^='R']",
    ]
    for sel in selectors:
        for li in soup.select(sel):
            if not li.get_text(strip=True):
                continue
            base = extract_from_li(li)
            out.append(augment_from_raw(base))
        if out:
            break
    return out

# ======================================================================================
# Registration
# ======================================================================================
# Meta registration (direct host + common proxy patterns)
register_meta(
    r"(?:^|\.)sciencedirect\.com$",
    extract_sciencedirect_meta,
    where="host",
    name="ScienceDirect meta",
)
register_meta(
    r"sciencedirect[-\.]",
    extract_sciencedirect_meta,
    where="url",
    name="ScienceDirect meta (proxy)",
)
# References registration
register(
    r"(?:^|\.)sciencedirect\.com$",
    parse_sciencedirect,
    where="host",
    name="ScienceDirect references",
)
register(
    r"sciencedirect[-\.]", parse_sciencedirect, where="url", name="ScienceDirect references (proxy)"
)
