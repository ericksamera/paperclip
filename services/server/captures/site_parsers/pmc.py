# services/server/captures/site_parsers/pmc.py
from __future__ import annotations

import re
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import (
    KEYWORDS_PREFIX_RX,
    augment_from_raw,
    collect_paragraphs_subtree,
    dedupe_keep_order,
    dedupe_section_nodes,
    extract_from_li,
    heading_text,
    split_keywords_block,
)


"""
PubMed Central (PMC) parser
---------------------------

Goals
- Robustly extract abstract, keywords, and full-text sections across PMC HTML variants.
- Harvest references and enrich with DOI / PMID / PMCID when available.
- Ignore figure/caption/aside noise and inline 'Keywords:' inside the abstract.
- Black/ruff friendly.

Public API
- extract_pmc_meta(url, dom_html) -> dict[str, object]
- parse_pmc(url, dom_html) -> list[dict[str, object]]

This module registers itself for host + common path patterns.
"""

# ======================================================================================
# Patterns / heuristics
# ======================================================================================

DOI_RX = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
PMID_RX = re.compile(r"\bpmid[:\s]*([0-9]{4,12})\b", re.I)
PMCID_RX = re.compile(r"\bpmcid[:\s]*([A-Z]*\d{3,})\b", re.I)

# Common non-content section titles
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg(e)?ments?|author(?:s)?(?:['’\s]|"
    r"\s*contributions?)|funding|competing interests?|conflicts? of interest|"
    r"ethics|data availability|declarations?|footnotes?|contributor information|"
    r"supplementary(?: information)?|associated data)\b",
    re.I,
)


def _txt(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _normalize_doi(s: str | None) -> str | None:
    if not s:
        return None
    d = unquote(s).strip()
    d = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", d, flags=re.I)
    return d.strip(" .;,").lower() or None


def _is_junk_text(s: str) -> bool:
    # UI crumbs frequently embedded in PMC blocks
    return bool(re.fullmatch(r"(view|open|download)\s+(figure|image|table)", s, re.I))


def _is_figure_descendant(node: Tag) -> bool:
    return bool(node.find_parent(["figure", "figcaption", "table", "aside", "footer"]))


# ======================================================================================
# References
# ======================================================================================
def _extract_ids_from_block(block: Tag) -> dict[str, str]:
    """
    Pull DOI / PMID / PMCID from a reference LI's text and anchors.
    """
    raw = block.get_text(" ", strip=True)
    out: dict[str, str] = {}

    # 1) DOI from anchors or raw text
    for a in block.find_all("a", href=True):
        m = DOI_RX.search(a.get("href", "")) or DOI_RX.search(
            a.get_text(" ", strip=True)
        )
        if m:
            out["doi"] = _normalize_doi(m.group(0)) or ""
            break
    if "doi" not in out:
        m = DOI_RX.search(raw)
        if m:
            out["doi"] = _normalize_doi(m.group(0)) or ""

    # 2) PMID / PMCID (anchors or raw)
    for a in block.find_all("a", href=True):
        t = a.get_text(" ", strip=True)
        href = a["href"]
        m1 = PMID_RX.search(t) or PMID_RX.search(href)
        m2 = PMCID_RX.search(t) or PMCID_RX.search(href)
        if m1 and "pmid" not in out:
            out["pmid"] = m1.group(1)
        if m2 and "pmcid" not in out:
            out["pmcid"] = m2.group(1)
    if "pmid" not in out:
        m = PMID_RX.search(raw)
        if m:
            out["pmid"] = m.group(1)
    if "pmcid" not in out:
        m = PMCID_RX.search(raw)
        if m:
            out["pmcid"] = m.group(1)

    return out


def parse_pmc(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Extract references from PMC pages and enrich with identifiers.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: list[dict[str, object]] = []

    selectors = [
        # Canonical PMC references containers
        "section.ref-list li",
        ".ref-list li",
        "ol.ref-list li",
        "ul.ref-list li",
        # Fallbacks
        "ol.references li",
        "ul.references li",
        "li[id^='ref'], li.reference",
    ]
    items: list[Tag] = []
    for sel in selectors:
        items = soup.select(sel)
        if items:
            break

    for li in items:
        if not li.get_text(strip=True):
            continue
        base = extract_from_li(li)  # {"raw": "...", maybe bits}
        rec = augment_from_raw(base)

        ids = _extract_ids_from_block(li)
        if ids.get("doi") and not rec.get("doi"):
            rec["doi"] = ids["doi"]
        # Provide convenient links
        if ids:
            links: dict[str, str] = rec.get("links", {}) or {}
            if ids.get("doi"):
                links["doi"] = f"https://doi.org/{ids['doi']}"
            if ids.get("pmid"):
                links["pmid"] = f"https://www.ncbi.nlm.nih.gov/pubmed/{ids['pmid']}/"
            if ids.get("pmcid"):
                links["pmc"] = (
                    f"https://www.ncbi.nlm.nih.gov/pmc/articles/{ids['pmcid']}/"
                )
            rec["links"] = links
        out.append(rec)

    return out


# ======================================================================================
# Meta / Sections
# ======================================================================================
def _abstract_host(soup: BeautifulSoup) -> Tag | None:
    """
    Find the abstract container. PMC variants include:
      - <section class="abstract" id="Abs1"> or id="abstract1"
      - <div class="abstract"> … </div>
      - Heading 'Abstract' followed by paragraphs
    """
    for sel in [
        "section.abstract",
        "section#Abs1",
        "section[id^='abs' i]",
        "div.abstract",
        "div#Abs1",
        "div[id^='abs' i]",
    ]:
        el = soup.select_one(sel)
        if el:
            return el
    # Heading fallback
    for h in soup.find_all(["h2", "h3", "h4"]):
        if re.fullmatch(r"\s*abstract\s*", heading_text(h), re.I):
            return h.parent if isinstance(h.parent, Tag) else h
    return None


def _extract_pmc_abstract(soup: BeautifulSoup) -> str | None:
    host = _abstract_host(soup)
    if not host:
        return None
    paras: list[str] = []
    for p in host.find_all("p"):
        if _is_figure_descendant(p):
            continue
        text = _txt(p.get_text(" ", strip=True))
        # Skip inline "Keywords:" paragraph often embedded in abstract
        if KEYWORDS_PREFIX_RX.match(text):
            continue
        if text and not _is_junk_text(text):
            paras.append(text)
    return " ".join(paras) if paras else None


def _extract_pmc_keywords(soup: BeautifulSoup) -> list[str]:
    """
    PMC commonly uses:
      <sec class="kwd-group"> <p><strong>Keywords:</strong> foo; bar …</p>
    """
    # 1) Structured keywords hosts
    for host in soup.select(
        "section.kwd-group, sec.kwd-group, div.kwd-group, div.kwdGroup"
    ):
        texts = [
            el.get_text(" ", strip=True) for el in host.find_all(["p", "li", "span"])
        ]
        blob = " | ".join(t for t in texts if t)
        if blob:
            items = split_keywords_block(blob)
            return dedupe_keep_order(items)

    # 2) Fallback: inline "Keywords: ..." anywhere
    m = soup.find(string=KEYWORDS_PREFIX_RX)
    if isinstance(m, str):
        return dedupe_keep_order(split_keywords_block(m))

    return []


def _main_wrapper(soup: BeautifulSoup) -> Tag:
    """
    Prefer a main/article wrapper if present to limit section scanning.
    """
    return (
        soup.find("article") or soup.find("main") or soup.find(id="maincontent") or soup
    )


def _collect_section_paras(root: Tag) -> list[str]:
    out: list[str] = []
    # Prefer <p> and list items in this subtree; ignore figure-like regions.
    for p in root.find_all("p"):
        if _is_figure_descendant(p):
            continue
        t = _txt(p.get_text(" ", strip=True))
        if t and not _is_junk_text(t):
            out.append(t)
    for li in root.find_all("li"):
        if _is_figure_descendant(li):
            continue
        t = _txt(li.get_text(" ", strip=True))
        if t and not _is_junk_text(t):
            out.append(t)
    # Fallback to broad subtree collection if nothing was found
    if not out:
        for t in collect_paragraphs_subtree(root):
            tt = _txt(t)
            if tt and not _is_junk_text(tt):
                out.append(tt)
    return out


def _pmc_section_nodes(wrapper: Tag) -> list[dict[str, object]]:
    """
    Strategy:
      - Use explicit section titles (class 'pmc_sec_title') when available.
      - Otherwise segment by H2/H3/H4 headings within the wrapper.
      - Skip 'Abstract' and admin-like sections via _NONCONTENT_RX.
    """
    nodes: list[dict[str, object]] = []

    # Prefer explicit PMC section title nodes
    titled = wrapper.select(".pmc_sec_title")
    headings = titled or wrapper.find_all(["h2", "h3", "h4"])

    for idx, h in enumerate(headings):
        title = heading_text(h)
        if (
            not title
            or re.fullmatch(r"\s*abstract\s*", title, re.I)
            or _NONCONTENT_RX.search(title)
        ):
            continue

        # Determine the end boundary: next heading of similar level (or any)
        end = None
        for k in range(idx + 1, len(headings)):
            end = headings[k]
            break

        # Build a temporary container of siblings between h and end
        # (avoid mutating original DOM)
        tmp_soup = BeautifulSoup("", "html.parser")
        container: Tag = tmp_soup.new_tag("div")
        sib = h.next_sibling
        while sib and sib is not end:
            if isinstance(sib, Tag):
                container.append(sib)
            sib = getattr(sib, "next_sibling", None)

        paras = _collect_section_paras(container)
        node: dict[str, object] = {"title": title}
        if paras:
            node["paragraphs"] = paras
        if node.get("paragraphs"):
            nodes.append(node)

    # If there is no explicit "Introduction", synthesize from lead-in text
    has_intro = any(
        isinstance(n.get("title"), str) and n["title"].strip().lower() == "introduction"
        for n in nodes
    )
    if not has_intro:
        # Lead-in: paragraphs after abstract and before the first heading
        leadin: list[str] = []
        first_head = headings[0] if headings else None
        start = _abstract_host(wrapper) or wrapper
        cur = getattr(start, "next_sibling", None)
        while cur and cur is not first_head:
            if isinstance(cur, Tag):
                for p in cur.find_all("p"):
                    if _is_figure_descendant(p):
                        continue
                    t = _txt(p.get_text(" ", strip=True))
                    if t and not _is_junk_text(t):
                        leadin.append(t)
            cur = getattr(cur, "next_sibling", None)
        if leadin:
            nodes.insert(0, {"title": "Introduction", "paragraphs": leadin})

    return dedupe_section_nodes(nodes)


def _extract_pmc_sections(soup: BeautifulSoup) -> list[dict[str, object]]:
    wrapper = _main_wrapper(soup)
    return _pmc_section_nodes(wrapper)


def extract_pmc_meta(_url: str, dom_html: str) -> dict[str, object]:
    """
    Return {"abstract": str|None, "keywords": [str], "sections": [ {title, paragraphs} ]}.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abstract = _extract_pmc_abstract(soup)
    keywords = _extract_pmc_keywords(soup)
    sections = _extract_pmc_sections(soup)
    return {"abstract": abstract, "keywords": keywords, "sections": sections}


# ======================================================================================
# Registrations
# ======================================================================================
# References (host + path)
register(
    r"(?:^|\.)pmc\.ncbi\.nlm\.nih\.gov$", parse_pmc, where="host", name="PMC references"
)
register(
    r"ncbi\.nlm\.nih\.gov/.*/pmc/|/pmc/",
    parse_pmc,
    where="url",
    name="PMC references (path)",
)

# Meta/sections (host + path)
register_meta(
    r"(?:^|\.)pmc\.ncbi\.nlm\.nih\.gov$",
    extract_pmc_meta,
    where="host",
    name="PMC meta",
)
register_meta(
    r"ncbi\.nlm\.nih\.gov/.*/pmc/|/pmc/",
    extract_pmc_meta,
    where="url",
    name="PMC meta (path)",
)
