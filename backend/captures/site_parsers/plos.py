# services/server/captures/site_parsers/plos.py
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import (
    DOI_RE,
    YEAR_RE,
    augment_from_raw,
    collapse_spaces,
    dedupe_keep_order,
    dedupe_section_nodes,
    heading_text,
)

# -------------------------- small helpers --------------------------
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg|conflict of interest|funding|data availability|"
    r"author contributions?)\b",
    re.I,
)
PMID_RE = re.compile(r"\bpmid:(\d+)\b", re.I)


# e.g. "170-5" → "170-175"
def _normalize_pages(pages: str) -> str:
    if not pages:
        return pages
    s = pages.strip().replace("\u2013", "-")  # en dash to hyphen
    # Leave complex page strings like "2312-2320.e5" alone
    m = re.fullmatch(r"(\d+)-(\d+)", s)
    if m:
        a, b = m.group(1), m.group(2)
        if len(b) < len(a):
            b = a[: len(a) - len(b)] + b
            return f"{a}-{b}"
        return s
    return s


def _txt(x: str | None) -> str:
    return collapse_spaces(x)


def _is_section(tag: Tag) -> bool:
    if not isinstance(tag, Tag) or tag.name != "div":
        return False
    classes = tag.get("class") or []
    return ("section" in classes) and ("toc-section" in classes)


# For common abbreviations → long journal names (kept conservative; we also store the short form)
_JOURNAL_ALIASES = {
    "Nat Methods": "Nature Methods",
    "Nat Biotechnol": "Nature Biotechnology",
    "Nat Genet": "Nature Genetics",
    "Nat Plants": "Nature Plants",
    "Nat Ecol Evol": "Nature Ecology & Evolution",
    "Curr Biol": "Current Biology",
    "Curr Opin Biotechnol": "Current Opinion in Biotechnology",
    "Curr Opin Plant Biol": "Current Opinion in Plant Biology",
    "Mol Phylogenet Evol": "Molecular Phylogenetics and Evolution",
    "Plant Physiol": "Plant Physiology",
    "Am J Bot": "American Journal of Botany",
    "Proc Natl Acad Sci U S A": "Proceedings of the National Academy of Sciences",
    "Plant Soil": "Plant and Soil",
    "BMC Genomics": "BMC Genomics",
    "Planta": "Planta",
    "Appl Biosci": "Applied Biosciences",
    "Nat Plants.": "Nature Plants",
}


# -------------------------- Abstract & Keywords --------------------------
def _extract_abstract(soup: BeautifulSoup) -> str | None:
    # Typical PLOS abstract is also "section toc-section" with <h2>Abstract</h2>
    for sec in soup.select("div.section.toc-section"):
        title = heading_text(sec.find(["h2", "h3", "h4"], recursive=False))
        if re.search(r"\babstract\b", title or "", re.I):
            paras = _collect_paragraphs_excluding_child_sections(sec)
            if paras:
                return " ".join(paras)
    # Fallback explicit containers
    for host in soup.select(
        "div#abstract, section#abstract, div[class*='abstract' i], section[class*='abstract' i]"
    ):
        paras = [p.get_text(" ", strip=True) for p in host.find_all("p")]
        paras = [_txt(p) for p in paras if p and len(p.strip()) > 1]
        if paras:
            return " ".join(paras)
    # Fallback: heading "Abstract" → following paragraphs
    head = soup.find(
        lambda t: isinstance(t, Tag)
        and t.name in {"h2", "h3", "h4"}
        and re.search(r"\babstract\b", heading_text(t), re.I)
    )
    if head:
        out = []
        sib = head.next_sibling
        while sib and not (isinstance(sib, Tag) and sib.name in {"h2", "h3", "h4"}):
            if isinstance(sib, Tag):
                if sib.name == "p":
                    t = _txt(sib.get_text(" ", strip=True))
                    if t:
                        out.append(t)
                else:
                    for p in sib.find_all("p"):
                        t = _txt(p.get_text(" ", strip=True))
                        if t:
                            out.append(t)
            sib = getattr(sib, "next_sibling", None)
        if out:
            return " ".join(out)
    return None


def _extract_keywords(soup: BeautifulSoup) -> list[str]:
    # PLOS "Subject Areas" / keywords
    hosts = soup.select(
        "ul.subject-area, ul.subjectAreas, "
        "div[id*='subject-area' i], div[class*='subject-area' i], "
        "section[id*='subject' i], div[id*='subject' i]"
    )
    items: list[str] = []
    for host in hosts:
        items += [a.get_text(" ", strip=True) for a in host.select("a, li, span")]
    if not items:
        # Simple "Keywords: ..."
        p = soup.find(string=re.compile(r"^\s*Keywords?\s*:", re.I))
        if isinstance(p, str):
            text = re.sub(r"^\s*Keywords?\s*:\s*", "", p, flags=re.I)
            items = [x.strip() for x in re.split(r"[;,/]|[\r\n]+", text) if x.strip()]
    items = [_txt(t) for t in items if t and len(t.strip()) > 1]
    return dedupe_keep_order(items)


# -------------------------- Section parsing --------------------------
def _collect_paragraphs_excluding_child_sections(sec: Tag) -> list[str]:
    out: list[str] = []
    for p in sec.find_all("p"):
        par_sec = p.find_parent(lambda t: _is_section(t))
        if par_sec is not None and par_sec is not sec:
            continue
        t = _txt(p.get_text(" ", strip=True))
        if t:
            out.append(t)
    for li in sec.find_all("li"):
        li_sec = li.find_parent(lambda t: _is_section(t))
        if li_sec is not None and li_sec is not sec:
            continue
        t = _txt(li.get_text(" ", strip=True))
        if t:
            out.append(t)
    return out


def _parse_plos_section(sec: Tag) -> dict[str, object]:
    h = sec.find(["h2", "h3", "h4"], recursive=False) or sec.find(["h2", "h3", "h4"])
    title = heading_text(h) if h else ""
    if title and _NONCONTENT_RX.search(title):
        return {}
    node: dict[str, object] = {
        "title": title,
        "paragraphs": _collect_paragraphs_excluding_child_sections(sec),
    }
    children: list[dict[str, object]] = []
    for child in sec.find_all("div", recursive=False):
        if not _is_section(child):
            continue
        kid = _parse_plos_section(child)
        if kid and (kid.get("title") or kid.get("paragraphs") or kid.get("children")):
            children.append(kid)
    if children:
        node["children"] = children
    return node


def _extract_sections(soup: BeautifulSoup) -> list[dict[str, object]]:
    top_nodes = []
    for sec in soup.select("div.section.toc-section"):
        if sec.find_parent(
            "div",
            class_=lambda cs: isinstance(cs, list)
            and "section" in cs
            and "toc-section" in cs,
        ):
            continue
        top_nodes.append(sec)
    out: list[dict[str, object]] = []
    for sec in top_nodes:
        node = _parse_plos_section(sec)
        if node and (
            node.get("title") or node.get("paragraphs") or node.get("children")
        ):
            out.append(node)
    return dedupe_section_nodes(out)


# -------------------------- References parsing --------------------------
# Strict PLOS-shaped reference:
#   "<AUTHORS>. <TITLE>. <JOURNAL>. <YEAR>;<VOL>(<ISS>):<PAGES>."
_PLOS_CIT_RX = re.compile(
    r"^\s*(?P<authors>.+?)\.\s+(?P<title>.+?)\.\s+(?P<journal>[^.;]+?)\.\s+"
    r"(?P<year>(?:19|20)\d{2})\s*;\s*(?P<volume>\d+)"
    r"(?:\((?P<issue>[^)]+)\))?\s*:\s*(?P<pages>[\d\u2013\-\.eE]+)",
    re.I,
)


def _clean_li_and_get_bits(li: Tag) -> dict[str, str]:
    # position number
    position = ""
    ord_span = li.find("span", class_="order")
    if ord_span:
        mpos = re.search(r"(\d+)", ord_span.get_text())
        if mpos:
            position = mpos.group(1)
        ord_span.decompose()
    # Extract & remove reflinks to keep raw text clean
    doi = ""
    doi_url = ""
    reflinks = li.find("ul", class_="reflinks")
    if reflinks:
        d = (reflinks.get("data-doi") or "").strip()
        if d:
            doi = d
            doi_url = f"https://doi.org/{d}"
        if not doi:
            for a in reflinks.find_all("a", href=True):
                m = DOI_RE.search(a["href"]) or DOI_RE.search(
                    a.get_text(" ", strip=True)
                )
                if m:
                    doi = m.group(0)
                    doi_url = "https://doi.org/" + doi
                    break
        reflinks.decompose()
    # Build raw text and peel off trailing PMID
    raw = collapse_spaces(li.get_text(" ", strip=True))
    pmid = ""
    mpm = PMID_RE.search(raw)
    if mpm:
        pmid = mpm.group(1)
        raw = collapse_spaces(PMID_RE.sub("", raw))
    # Drop any leading "36." residue that might remain
    raw = re.sub(r"^\s*\d+\.\s*", "", raw)
    return {
        "raw": raw,
        "pmid": pmid,
        "doi": doi,
        "doi_url": doi_url,
        "position": position,
    }


def _authors_string_to_list(authors_str: str) -> list[dict[str, str]]:
    """
    Heuristic author splitter for 'Surname XX, Surname YY, ..., et al'
    Produces [{'family': 'Cheng', 'given': 'H'}, ...]
    """
    # remove trailing et al.
    a = re.sub(r",?\s*et al\.?$", "", authors_str.strip(), flags=re.I)
    parts = [p.strip() for p in a.split(",") if p.strip()]
    out: list[dict[str, str]] = []
    for p in parts:
        # Examples: "Koepfli K-P", "Moran JA", "de Folter S"
        m = re.match(
            r"(?P<family>.+?)\s+(?P<given>[A-Z][A-Za-z\-\.]*([A-Z][A-Za-z\-\.]*)?)$", p
        )
        if m:
            out.append(
                {
                    "family": m.group("family"),
                    "given": m.group("given").replace(".", ""),
                }
            )
        else:
            # fallback: everything as family
            out.append({"family": p, "given": ""})
    return out


def _apply_journal_alias(j: str) -> tuple[str, str]:
    js = j.strip().rstrip(".")
    long = _JOURNAL_ALIASES.get(js, js)
    short = js
    return long, short


def parse_plos(_url: str, dom_html: str) -> list[dict[str, object]]:
    """
    Extract references from PLOS pages:
      <div class="toc-section"><h2>References</h2><ol class="references"> <li>...</li> </ol></div>
    Priority:
      • DOI from data-doi / links
      • Strict PLOS pattern for title/journal/year/vol/issue/pages
      • PMID if present
      • Fallback augment_from_raw for oddballs (books, reports)
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: list[dict[str, object]] = []
    for li in soup.select("ol.references li, ul.references li"):
        bits = _clean_li_and_get_bits(li)
        raw = bits["raw"]
        doi = bits["doi"]
        doi_url = bits["doi_url"]
        pmid = bits["pmid"]
        position = bits["position"]
        # Stable id if present
        ref_id = li.get("id") or None
        if not ref_id:
            a_named = li.find("a", attrs={"name": True}) or li.find(
                "a", attrs={"id": True}
            )
            if a_named:
                ref_id = a_named.get("name") or a_named.get("id") or None
        # Start with a generic parse to get authors etc.
        base = {"raw": raw, "doi": doi, "ref_id": ref_id or ""}
        my = YEAR_RE.search(raw)
        if my:
            base["issued_year"] = my.group(0)
        ref = augment_from_raw(base)  # may fill title/authors/container_title/etc.
        # Tight PLOS-shaped parse to override title/container when we can
        m = _PLOS_CIT_RX.search(raw)
        if m:
            title = _txt(m.group("title"))
            journal_raw = _txt(m.group("journal"))
            year = m.group("year")
            vol = m.group("volume")
            iss = (m.group("issue") or "").strip()
            pgs = _normalize_pages(_txt(m.group("pages")))
            # Put clean fields
            ref["title"] = title
            long_j, short_j = _apply_journal_alias(journal_raw)
            ref["container_title"] = long_j
            ref["container_title_short"] = short_j
            ref["issued_year"] = year
            ref["volume"] = vol
            if iss:
                ref["issue"] = iss
            if pgs:
                ref["page"] = pgs
                # try to split first/last
                mp = re.match(r"^(\d+)[\u2013-](\d+)$", pgs)
                if mp:
                    ref["page_first"] = mp.group(1)
                    ref["page_last"] = mp.group(2)
            # Authors: if augment didn't manage, or looks empty, add ours
            if not ref.get("author"):
                ref["author"] = _authors_string_to_list(m.group("authors"))
        # PMID, DOI url, position
        if pmid and not ref.get("pmid"):
            ref["pmid"] = pmid
        if doi and not ref.get("DOI"):
            # some parts of the app expect uppercase DOI key; keep both
            ref["DOI"] = doi
        if doi_url and not ref.get("url"):
            ref["url"] = doi_url
        if position:
            try:
                ref["position"] = int(position)
            except Exception:
                ref["position"] = position
        out.append(ref)
    return out


# -------------------------- public entry (meta/sections) --------------------------
def extract_plos_meta(_url: str, dom_html: str) -> dict[str, object]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abstract = _extract_abstract(soup)
    keywords = _extract_keywords(soup)
    sections = _extract_sections(soup)
    return {"abstract": abstract, "keywords": keywords, "sections": sections}


# -------------------------- registrations --------------------------
# Meta
register_meta(r"(?:^|\.)plos\.org$", extract_plos_meta, where="host", name="PLOS meta")
register_meta(
    r"(?:journals[-\.]plos|plosone|plosbiology|ploscompbiol|plosgenetics|plospathogens)",
    extract_plos_meta,
    where="url",
    name="PLOS meta (path)",
)
# References
register(r"(?:^|\.)plos\.org$", parse_plos, where="host", name="PLOS references")
register(
    r"(?:journals[-\.]plos|plosone|plosbiology|ploscompbiol|plosgenetics|plospathogens)",
    parse_plos,
    where="url",
    name="PLOS references (path)",
)
