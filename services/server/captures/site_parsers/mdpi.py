# services/server/captures/site_parsers/mdpi.py
from __future__ import annotations

import re
from typing import cast

from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import (
    DOI_RE,
    YEAR_RE,
    augment_from_raw,
    collapse_spaces,
    collect_paragraphs_subtree,
    dedupe_keep_order,
    dedupe_section_nodes,
    heading_text,
)

# -------------------------- small helpers --------------------------
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg(?:e)?ments?|conflicts?\s+of\s+interest|"
    r"competing\s+interests?|funding|data\s+availability|author(?:s)?\s+contributions?)\b",
    re.I,
)

def _txt(x: str | None) -> str:
    return collapse_spaces(x)

def _p_texts(host: Tag) -> list[str]:
    """Collect visible paragraph-like text under an MDPI block."""
    out: list[str] = []
    # MDPI renders paragraphs in <div class="html-p"> and regular <p>
    for sel in ["div.html-p", "p"]:
        for p in host.select(sel):
            t = _txt(p.get_text(" ", strip=True))
            if t:
                out.append(t)
    # bullet items too
    for li in host.find_all("li"):
        t = _txt(li.get_text(" ", strip=True))
        if t:
            out.append(t)
    # last resort: subtree text (still filtered)
    if not out:
        for t in collect_paragraphs_subtree(host):
            tt = _txt(t)
            if tt:
                out.append(tt)
    return out

# -------------------------- Abstract --------------------------
def _extract_abstract_mdpi(soup: BeautifulSoup) -> str | None:
    # 1) Canonical MDPI abstract host
    host = soup.select_one("section#html-abstract, section.html-abstract, div.art-abstract")
    if host:
        paras = _p_texts(host)
        if paras:
            return " ".join(paras)
    # 2) Heading "Abstract"
    head = soup.find(lambda t: isinstance(t, Tag) and t.name in {"h2", "h3", "h4"}
                     and re.fullmatch(r"\s*abstract\s*", heading_text(t), re.I))
    if head:
        # take sibling container or paragraphs until next heading
        container = head.find_parent(["section", "div"]) or head.parent
        if isinstance(container, Tag):
            paras = _p_texts(container)
            if paras:
                return " ".join(paras)
    return None

# -------------------------- Keywords --------------------------
def _extract_keywords_mdpi(soup: BeautifulSoup) -> list[str]:
    # Preferred: the #html-keywords block with <a> chips
    host = soup.select_one("#html-keywords")
    items: list[str] = []
    if host:
        for a in host.select("a, li, span"):
            t = _txt(a.get_text(" ", strip=True))
            if t and not re.match(r"^\s*Keywords?:\s*$", t, re.I):
                items.append(t)
        if items:
            return dedupe_keep_order([re.sub(r"^\s*Keywords?\s*:\s*", "", i, flags=re.I) for i in items])
    # Fallback: any inline "Keywords:" text
    m = soup.find(string=re.compile(r"^\s*Keywords?\s*:", re.I))
    if isinstance(m, str):
        text = re.sub(r"^\s*Keywords?\s*:\s*", "", m, flags=re.I)
        parts = [p.strip(" .,:;/") for p in re.split(r"[;,/]|[\r\n]+", text) if p.strip()]
        return dedupe_keep_order(parts)
    return []

# -------------------------- Sections (nested) --------------------------
def _parse_mdpi_section(sec: Tag) -> dict[str, object] | None:
    # Titles are inside the first h2/h3/h4 within the section
    h = sec.find(["h2", "h3", "h4"])
    title = heading_text(h) if h else ""
    # Skip non-content & Abstract/References duplicates
    if not title or _NONCONTENT_RX.search(title) or re.fullmatch(r"\s*abstract\s*", title, re.I):
        # We still might keep paragraphs if no title but real text exists
        title = title or ""
    # Paragraphs that belong to this section
    paras = _p_texts(sec)
    # Immediate child sections -> recurse
    children: list[dict[str, object]] = []
    for child in sec.find_all("section", recursive=False):
        kid = _parse_mdpi_section(child)
        if kid and (kid.get("title") or kid.get("paragraphs") or kid.get("children")):
            children.append(kid)
    node: dict[str, object] = {}
    if title:
        node["title"] = title
    if paras:
        node["paragraphs"] = paras
    if children:
        node["children"] = children
    return node if (node.get("title") or node.get("paragraphs") or node.get("children")) else None

def _extract_sections_mdpi(soup: BeautifulSoup) -> list[dict[str, object]]:
    """
    MDPI full text lives under <div class="html-body"> containing nested <section id="sec..."> blocks.
    We build a tree from top-level sections (direct children).
    """
    wrapper = (
        soup.select_one("div.html-body")
        or soup.find("article")
        or soup.find("main")
        or soup
    )
    # top-level: direct child <section> elements that have any heading
    top_secs: list[Tag] = []
    for s in wrapper.find_all("section", recursive=False):
        if s.find(["h2", "h3", "h4"]):
            top_secs.append(s)
    # fallback: any section with id="sec..." not nested under another such section
    if not top_secs:
        for s in wrapper.find_all("section", id=re.compile(r"^sec", re.I)):
            par = s.find_parent("section")
            keep = True
            while par and par is not wrapper:
                if re.match(r"^sec", (par.get("id") or ""), re.I):
                    keep = False
                    break
                par = par.find_parent("section")
            if keep and s.find(["h2", "h3", "h4"]):
                top_secs.append(s)
    out: list[dict[str, object]] = []
    for sec in top_secs:
        node = _parse_mdpi_section(sec)
        if node and (node.get("title") or node.get("paragraphs") or node.get("children")):
            # Skip Abstract/References here; abstract is handled separately, references by the ref parser
            if re.fullmatch(r"\s*abstract\s*", str(node.get("title") or ""), re.I):
                continue
            if _NONCONTENT_RX.search(str(node.get("title") or "")):
                continue
            out.append(node)
    return dedupe_section_nodes(out)

# -------------------------- References --------------------------
def _reference_items_mdpi(soup: BeautifulSoup) -> list[Tag]:
    """
    Try multiple MDPI-ish layouts to find individual reference nodes.
    Order: citeproc blocks -> explicit references list -> generic lists.
    """
    # 1) citeproc style: <div class="csl-bib-body"><div class="csl-entry">...</div>...</div>
    bib = soup.select_one("div.csl-bib-body, section.csl-bib-body")
    if bib:
        items = [d for d in bib.find_all("div", class_=re.compile(r"\bcsl-entry\b", re.I))]
        if items:
            return items

    # 2) A "References" section area (by heading), then pick LIs or Ps inside
    for host in soup.select("section, div"):
        h = host.find(["h2", "h3", "h4"])
        if h and re.fullmatch(r"\s*references?\s*", heading_text(h), re.I):
            items = host.select("li")
            if items:
                return items
            ps = [p for p in host.find_all("p") if _txt(p.get_text(" ", strip=True))]
            if ps:
                return ps

    # 3) Generic fallbacks
    sel_list = [
        "ol.references li",
        "ul.references li",
        "section#references li",
        "div.references li",
        "li[id^='ref'], li[id^='B'], li[id^='R']",
    ]
    for sel in sel_list:
        items = soup.select(sel)
        if items:
            return items
    return []

def _extract_one_ref(node: Tag) -> dict[str, object] | None:
    # Raw line
    raw = _txt(node.get_text(" ", strip=True))
    if not raw:
        return None
    # DOI: prefer anchor href/text
    doi = ""
    for a in node.find_all("a", href=True):
        m = DOI_RE.search(a.get("href", "")) or DOI_RE.search(_txt(a.get_text(" ", strip=True)))
        if m:
            doi = m.group(0)
            break
    if not doi:
        m = DOI_RE.search(raw)
        if m:
            doi = m.group(0)
    base: dict[str, object] = {"raw": raw, "doi": doi}
    my = YEAR_RE.search(raw)
    if my:
        base["issued_year"] = my.group(0)
    return augment_from_raw(base)

def parse_mdpi(_url: str, dom_html: str) -> list[dict[str, object]]:
    """Extract references from MDPI pages (robust across templates)."""
    soup = BeautifulSoup(dom_html or "", "html.parser")
    items = _reference_items_mdpi(soup)
    out: list[dict[str, object]] = []
    for it in items:
        ref = _extract_one_ref(it)
        if ref:
            out.append(ref)
    return out

# -------------------------- public entry (meta/sections) --------------------------
def extract_mdpi_meta(_url: str, dom_html: str) -> dict[str, object]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abstract = _extract_abstract_mdpi(soup)
    keywords = _extract_keywords_mdpi(soup)
    sections = _extract_sections_mdpi(soup)
    return {"abstract": abstract, "keywords": keywords, "sections": sections}

# -------------------------- registrations --------------------------
# Host + common path patterns
register_meta(r"(?:^|\.)mdpi\.com$", extract_mdpi_meta, where="host", name="MDPI meta")
register_meta(r"mdpi\.com/", extract_mdpi_meta, where="url", name="MDPI meta (path)")
register(r"(?:^|\.)mdpi\.com$", parse_mdpi, where="host", name="MDPI references")
register(r"mdpi\.com/", parse_mdpi, where="url", name="MDPI references (path)")
