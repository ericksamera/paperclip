# services/server/captures/site_parsers/oup.py
from __future__ import annotations

import re
from typing import cast
from collections.abc import Iterator
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import (
    DOI_RE,  # r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+"
    YEAR_RE,
    augment_from_raw,
    collapse_spaces,
    dedupe_keep_order,
    dedupe_section_nodes,
    extract_from_li,
    heading_text,
)

# -------------------------- helpers --------------------------
_NONCONTENT_RX = re.compile(
    r"\b("
    r"references?|literature\s+cited|acknowledg(?:e)?ments?|back\s*acknowledgements?|"
    r"conflicts?\s+of\s+interest|competing\s+interests?|ethics|funding|data\s+availability|"
    r"author(?:s)?\s+contributions?|footnotes?|supplementary(?:\s+material|\s+information)?)\b",
    re.I,
)

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
        and (h.name or "").lower() == "h2"
        and _has_class(h, "section-title", "js-splitscreen-section-title")
    )


def _is_hx_section_title(h: Tag) -> bool:
    return (
        isinstance(h, Tag)
        and (h.name or "").lower() in ("h2", "h3", "h4")
        and (
            _has_class(h, "section-title")
            or _has_class(h, "js-splitscreen-section-title")
        )
    )


def _is_abstract_h2(h: Tag) -> bool:
    return (
        isinstance(h, Tag)
        and (h.name or "").lower() == "h2"
        and (
            _has_class(h, "abstract-title")
            or re.search(r"\babstract\b", heading_text(h), re.I)
        )
    )


def _next_sibling_heading(start: Tag, names: tuple[str, ...]) -> Tag | None:
    cur = start.next_sibling
    names = tuple(n.lower() for n in names)
    while cur:
        if isinstance(cur, Tag) and (cur.name or "").lower() in names:
            return cur
        cur = cur.next_sibling
    return None


def _iter_between(start: Tag, end: Tag | None) -> Iterator[object]:
    cur = start.next_sibling
    while cur and cur is not end:
        yield cur
        cur = cur.next_sibling


def _collect_paragraphs_between(a: Tag, b: Tag | None) -> list[str]:
    out: list[str] = []
    for node in _iter_between(a, b):
        if not isinstance(node, Tag):
            continue
        if (node.name or "").lower() == "p":
            t = _txt(node.get_text(" ", strip=True))
            if t:
                out.append(t)
        elif (node.name or "").lower() in ("ul", "ol"):
            for li in node.find_all("li", recursive=False):
                t = _txt(li.get_text(" ", strip=True))
                if t:
                    out.append(t)
    return out


# -------------------------- Abstract --------------------------
def _extract_abstract(soup: BeautifulSoup) -> str | None:
    for host in soup.select("section.abstract, div.abstract"):
        paras = [p.get_text(" ", strip=True) for p in host.find_all("p")]
        paras = [_txt(p) for p in paras if p]
        if paras:
            return " ".join(paras)
    head = soup.find(_is_abstract_h2)
    if head:
        nxt = _next_sibling_heading(head, ("h2",))
        paras = _collect_paragraphs_between(head, nxt)
        if paras:
            return " ".join(paras)
    return None


# -------------------------- Keywords --------------------------
def _extract_keywords(soup: BeautifulSoup) -> list[str]:
    items: list[str] = []
    for a in soup.select(
        ".kwd-group a.kwd-part, .kwd-group span.kwd-part, "
        ".kwd-group a.kwd-main, .kwd-group span.kwd-main"
    ):
        t = _txt(a.get_text(" ", strip=True))
        if t:
            items.append(t)
    if not items:
        el = soup.find(string=re.compile(r"^\s*Keywords?\s*:", re.I))
        if isinstance(el, str):
            text = re.sub(r"^\s*Keywords?\s*:\s*", "", el, flags=re.I)
            parts = [x.strip() for x in re.split(r"[;,/]|[\r\n]+", text) if x.strip()]
            items.extend(parts)
    items = [x for x in items if x and len(x) > 1]
    return dedupe_keep_order(items)


# -------------------------- Sections --------------------------
def _article_root(soup: BeautifulSoup) -> Tag:
    return soup.select_one("[data-widgetname='ArticleFulltext']") or soup


def _first_content_h2(soup: BeautifulSoup) -> Tag | None:
    for h in soup.find_all("h2"):
        if _is_h2_section_title(h) and not re.search(
            r"\babstract\b", heading_text(h), re.I
        ):
            return h
    return None


def _extract_headless_leadin(soup: BeautifulSoup) -> list[str]:
    root = _article_root(soup)
    first_h2 = _first_content_h2(soup)
    seen_abstract = False
    leadin: list[str] = []
    abstract_host = soup.select_one("section.abstract, div.abstract")
    abstract_h2 = soup.find(_is_abstract_h2)
    for el in root.descendants:
        if not isinstance(el, Tag):
            continue
        if el is abstract_host or el is abstract_h2:
            seen_abstract = True
            continue
        if first_h2 is not None and el is first_h2:
            break
        if not seen_abstract:
            continue
        if (el.name or "").lower() == "p":
            if el.find_parent(["figure", "figcaption", "table", "thead", "tbody"]):
                continue
            if el.find_parent(class_=_EXCLUDE_PARENTS_RX):
                continue
            t = _txt(el.get_text(" ", strip=True))
            if t and len(t) > 40:
                leadin.append(t)
    uniq, seen = [], set()
    for p in leadin:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _extract_sections(soup: BeautifulSoup) -> list[dict[str, object]]:
    leadin_paras = _extract_headless_leadin(soup)
    h2s = [h for h in soup.find_all("h2") if _is_h2_section_title(h)]
    h2s = [h for h in h2s if not re.search(r"\babstract\b", heading_text(h), re.I)]
    out: list[dict[str, object]] = []
    for i, h2 in enumerate(h2s):
        title = heading_text(h2)
        if not title or _NONCONTENT_RX.search(title):
            continue
        h2_end = h2s[i + 1] if i + 1 < len(h2s) else None
        child_heads: list[Tag] = []
        for node in _iter_between(h2, h2_end):
            if (
                isinstance(node, Tag)
                and (node.name or "").lower() in ("h3", "h4")
                and _is_hx_section_title(node)
            ):
                child_heads.append(node)
        first_child = child_heads[0] if child_heads else None
        parent_paras = _collect_paragraphs_between(h2, first_child or h2_end)
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


# -------------------------- References: identifiers & clean text --------------------------
# We intentionally EXTRACT identifiers BEFORE removing the "citation-links" UI box.

_DOI_HINT_SEL = (
    # explicit doi/crossref blocks and common anchors
    "a.link-doi, .crossref-doi a, a[href*='doi.org'], a[href*='dx.doi.org'], "
    "a[href*='/doi/10.'], a[href*='10.']"
)


def _find_doi_in_attrs(tag: Tag) -> str | None:
    # scan any attr that might contain a DOI-ish string (href, data-targetid, data-doi)
    for attr in ("href", "data-targetid", "data-doi", "data-dx-doi", "title"):
        v = tag.get(attr)
        if not v:
            continue
        s = unquote(v)
        m = DOI_RE.search(s)
        if m:
            return m.group(0)
    return None


def _extract_doi_anywhere(container: Tag) -> str | None:
    # 1) scan helpful anchors first
    for a in container.select(_DOI_HINT_SEL):
        doi = _find_doi_in_attrs(a)
        if doi:
            return doi
        # sometimes the text itself is "10.xxxx/..." (rare)
        m = DOI_RE.search(a.get_text(" ", strip=True) or "")
        if m:
            return m.group(0)
    # 2) Silverchair exposes a percent-encoded DOI in the OpenURL holder
    for span in container.select(".inst-open-url-holders, [data-targetid]"):
        doi = _find_doi_in_attrs(span)
        if doi:
            return doi
    # 3) last resort: any DOI-looking token in the container text
    m = DOI_RE.search(container.get_text(" ", strip=True))
    return m.group(0) if m else None


def _extract_pmid(container: Tag) -> str | None:
    for a in container.select("a[href*='ncbi.nlm.nih.gov/pubmed/'], a.link-pub-id"):
        href = a.get("href") or ""
        m = re.search(r"/pubmed/(\d+)", href)
        if m:
            return m.group(1)
    return None


def _extract_pmcid(container: Tag) -> str | None:
    for a in container.select("a[href*='ncbi.nlm.nih.gov/pmc/articles/PMC']"):
        href = a.get("href") or ""
        m = re.search(r"/pmc/articles/(PMC\d+)", href, re.I)
        if m:
            return m.group(1).upper()
    return None


def _strip_ref_noise(tag: Tag) -> None:
    # remove UI chrome AFTER we've harvested ids
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


def parse_oup(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Extract references from Oxford Academic (Silverchair) pages, including:
      • split-view ref list (.ref-list .ref-content)
      • classic <ol/ul class="references"> forms

    Adds: rec['doi'] (normalized), rec['links']['doi'], and PubMed/PMCID when present.
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

        # ----- 1) Harvest identifiers BEFORE stripping link boxes -----
        doi = _extract_doi_anywhere(node)
        pmid = _extract_pmid(node)
        pmcid = _extract_pmcid(node)

        # ----- 2) Clean UI chrome and get raw text -----
        _strip_ref_noise(node)
        raw = _txt(node.get_text(" ", strip=True))
        if not raw:
            continue

        rec: dict[str, object] = {"raw": raw}
        if doi:
            rec["doi"] = doi
        if pmid:
            rec["pmid"] = pmid
        if pmcid:
            rec["pmcid"] = pmcid

        # Optional year (if exposed via a tagged <div class="year">)
        y_el = node.find(class_=re.compile(r"\byear\b", re.I))
        if y_el:
            y_txt = _txt(y_el.get_text(" ", strip=True))
            m = YEAR_RE.search(y_txt) if y_txt else None
            if m:
                rec["year"] = m.group(0)

        # Friendly links map
        links: dict[str, str] = {}
        if rec.get("doi"):
            links["doi"] = f"https://doi.org/{rec['doi']}"
        if pmid:
            links["pubmed"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        if pmcid:
            links["pmc"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
        if links:
            rec["links"] = links

        out.append(augment_from_raw(rec))

    # Fallback: list-based references (rare on OUP)
    if not out:
        for sel in [
            "ol.references li",
            "ul.references li",
            "section#references li",
            "section.references li",
            "li[id^='ref']",
            "li[id^='B']",
            "li[id^='R']",
        ]:
            items = soup.select(sel)
            for li in items:
                if not li.get_text(strip=True):
                    continue
                # Try to capture DOI first
                doi = _extract_doi_anywhere(li)
                pmid = _extract_pmid(li)
                pmcid = _extract_pmcid(li)
                # Clean chrome then text
                _strip_ref_noise(li)
                base = extract_from_li(li)  # includes 'raw'
                rec = augment_from_raw(base)
                if doi:
                    rec["doi"] = doi
                if pmid:
                    rec["pmid"] = pmid
                if pmcid:
                    rec["pmcid"] = pmcid
                links: dict[str, str] = {}
                if doi:
                    links["doi"] = f"https://doi.org/{doi}"
                if pmid:
                    links["pubmed"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                if pmcid:
                    links["pmc"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
                if links:
                    rec["links"] = links
                out.append(rec)
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
register_meta(
    r"(?:^|\.)academic\.oup\.com$", extract_oup_meta, where="host", name="OUP meta"
)
register_meta(r"oup\.com/", extract_oup_meta, where="url", name="OUP meta (path)")

# References
register(r"(?:^|\.)academic\.oup\.com$", parse_oup, where="host", name="OUP references")
register(r"oup\.com/", parse_oup, where="url", name="OUP references (path)")

# Proxy-friendly routes (e.g., academic-oup-com.ezproxy.*, doi-org/ dx.doi.org via proxy hops)
register_meta(
    r"academic[-\.]oup[-\.]com|oup[-\.]com",
    extract_oup_meta,
    where="url",
    name="OUP meta (proxy)",
)
register(
    r"academic[-\.]oup[-\.]com|oup[-\.]com",
    parse_oup,
    where="url",
    name="OUP references (proxy)",
)
