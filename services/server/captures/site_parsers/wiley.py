# services/server/captures/site_parsers/wiley.py
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import (
    heading_text, paras_between, collect_paragraphs_subtree, dedupe_keep_order,
    collect_paras_excluding, dedupe_section_nodes
)

DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>),;]+", re.I)

# -------------------------- tiny utils --------------------------

def norm_space(s: Optional[str]) -> str:
    return re.compile(r"\s+").sub(" ", s).strip() if s else ""

def normalize_dash(s: str) -> str:
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    s = re.compile(r"\s*-\s*").sub("-", s)
    return s.strip(" -\t")

def take_text(node: Optional[Tag]) -> str:
    return norm_space(node.get_text(" ", strip=True)) if node is not None else ""

def is_icon_i(tag: Tag) -> bool:
    if not isinstance(tag, Tag) or tag.name != "i":
        return False
    classes = tag.get("class") or []
    return any("icon" in (c or "") for c in classes)

def clean_doi(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    x = raw.strip()
    x = re.compile(r"(?i)^\s*doi:\s*").sub("", x)
    x = re.compile(r"(?i)^https?://(?:dx\.)?doi\.org/").sub("", x)
    x = x.strip().strip(".,;)]}")
    x = x.lower()
    return x or None

# -------------------------- LI → reference dict --------------------------

def extract_doi(li: Tag) -> Optional[str]:
    # 1) hidden span
    doi_span = li.find("span", class_=lambda c: bool(c and "data-doi" in c))
    if doi_span:
        d = clean_doi(take_text(doi_span))
        if d:
            return d

    # 2) DOI-looking <a class="accessionId"> text or href
    acc = li.find("a", class_=lambda c: bool(c and "accessionId" in c))
    if acc:
        txt = take_text(acc)
        m = DOI_RE.search(txt) or DOI_RE.search(acc.get("href") or "")
        if m:
            return clean_doi(m.group(0))

    # 3) any DOI-looking token in the LI
    raw = li.get_text(" ", strip=True)
    m = DOI_RE.search(raw)
    return clean_doi(m.group(0)) if m else None

def extract_pages(li: Tag) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    p_first = take_text(li.find("span", class_="pageFirst")) or None
    p_last = take_text(li.find("span", class_="pageLast")) or None
    if p_first and p_last:
        pages = f"{normalize_dash(p_first)}-{normalize_dash(p_last)}"
    else:
        pages = normalize_dash(p_first or p_last or "") or None
    return (p_first, p_last, pages)

def parse_author_list(li: Tag) -> List[str]:
    out: List[str] = []
    for a in li.find_all("span", class_="author"):
        txt = take_text(a)
        if txt:
            out.append(txt)
    # de-dup, preserve order
    seen, uniq = set(), []
    for a in out:
        la = a.lower()
        if la not in seen:
            seen.add(la)
            uniq.append(a)
    return uniq

def extract_title_and_type(li: Tag) -> Tuple[Optional[str], Optional[str], Optional[Tag]]:
    """
    Returns (title, type, title_tag), where type ∈ {'article', 'chapter', 'book', None}.
    Prefers Wiley's explicit spans when present.
    """
    t_article = li.find("span", class_="articleTitle")
    t_chapter = li.find("span", class_="chapterTitle")
    t_book = li.find("span", class_="bookTitle")

    if t_article:
        return take_text(t_article), "article", t_article
    if t_chapter and t_book:
        return take_text(t_chapter), "chapter", t_chapter
    if t_book:
        return take_text(t_book), "book", t_book
    return None, None, None

def extract_container_after_title(li: Tag, title_tag: Optional[Tag]) -> Optional[str]:
    """
    Wiley often italicizes genus/species inside the title (<i>…</i>), then puts the journal/book name
    as an italicized sibling *after* the title node. We must skip <i> tags *inside* the title.
    """
    if title_tag:
        for sib in title_tag.next_siblings:
            if isinstance(sib, Tag):
                # direct italic sibling?
                if sib.name == "i" and not is_icon_i(sib):
                    txt = take_text(sib)
                    if txt:
                        return txt
                # otherwise, look inside this sibling
                i = sib.find("i", recursive=True)
                if i and not is_icon_i(i):
                    txt = take_text(i)
                    if txt:
                        return txt

    # Fallback: first non-icon <i> anywhere in the LI that is not contained by the title node
    for i_tag in li.find_all("i"):
        if is_icon_i(i_tag):
            continue
        if title_tag and title_tag in i_tag.parents:
            continue
        txt = take_text(i_tag)
        if txt:
            return txt
    return None

def parse_one_li(li: Tag) -> Optional[Dict[str, object]]:
    raw = norm_space(li.get_text(" ", strip=True))
    if not raw:
        return None

    authors = parse_author_list(li)
    year_txt = take_text(li.find("span", class_="pubYear"))
    year = int(year_txt) if year_txt.isdigit() else None

    title, rtype, title_tag = extract_title_and_type(li)
    container = extract_container_after_title(li, title_tag)

    vol = take_text(li.find("span", class_="vol")) or None
    issue = take_text(li.find("span", class_="issue")) or None
    p_first, p_last, pages = extract_pages(li)

    doi = extract_doi(li)
    url = f"https://doi.org/{doi}" if doi else None

    # For chapter entries, “container” is the book title
    if rtype == "chapter":
        book_title = take_text(li.find("span", class_="bookTitle"))
        container = book_title or container

    ref: Dict[str, object] = {"raw": raw}
    if authors: ref["authors"] = authors
    if year is not None: ref["year"] = year
    if title: ref["title"] = title
    if container: ref["container_title"] = container
    if vol: ref["volume"] = vol
    if issue: ref["issue"] = issue
    if p_first: ref["page_first"] = p_first
    if p_last: ref["page_last"] = p_last
    if pages: ref["pages"] = pages
    if doi: ref["doi"] = doi
    if url: ref["url"] = url
    if rtype: ref["type"] = rtype

    return ref

# -------------------------- selectors & references parser --------------------------

def _select_reference_items(soup: BeautifulSoup) -> List[Tag]:
    """
    Find the <li> elements holding references across Wiley templates, including the
    “pane-pcw-references” variant and the classic article references section.
    """
    # Explicit references sections
    sections = soup.select(
        "section.article-section__references, "
        "section#article-references-section-1, "
        "div.article-section__references, "
        "div#pane-pcw-references"
    )
    for sec in sections:
        items = sec.select("li[data-bib-id]")
        if items:
            return items

    # Other Wiley templates & safe fallbacks
    for sel in [
        "div#pane-pcw-references ul.rlist.separator li",
        "ul.rlist.separator li",
        "ol.references__list li",
        "ol.reference__list li",
        "ol.citation-list li",
        "ol.references li",
        "ul.references li",
        "section#references li",
    ]:
        items = soup.select(sel)
        if items:
            return items

    # Last resort: anything that looks like a ref item
    return soup.select("li[data-bib-id]")

def parse_wiley(_url: str, dom_html: str) -> List[Dict[str, object]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: List[Dict[str, object]] = []
    for li in _select_reference_items(soup):
        ref = parse_one_li(li)
        if ref:
            out.append(ref)
    return out

# -------------------------- Wiley: abstract / keywords / sections --------------------------

# NOTE: include "abbreviations" in NONCONTENT to avoid polluting sections with the list/table.
_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg|conflict of interest|funding|ethics|data availability|author contributions?|abbreviations?)\b",
    re.I,
)

def _txt(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()

def _looks_like_keywords_host(tag: Tag) -> bool:
    if not isinstance(tag, Tag):
        return False
    cid = (tag.get("id") or "").lower()
    cls = " ".join((tag.get("class") or [])).lower()
    return ("keyword" in cid) or ("keyword" in cls) or ("subject" in cls)

def _find_main_wrapper(soup: BeautifulSoup) -> Tag:
    """
    Prefer the wrapper that contains ALL body sections. Wiley has multiple shells; in the “metis” layout
    the body is under <section class="article-section article-section__full">.
    """
    return (
        soup.select_one("section.article-section__full")
        or soup.find("article")
        or soup.find("main")
        or soup
    )

def _extract_wiley_abstract(soup: BeautifulSoup) -> Optional[str]:
    """
    Robustly extract Abstract across classic and “metis” variants.
    """
    # 1) Any explicit abstract host (section/div) with 'abstract' in class or id
    for host in soup.select(
        "section#abstract, div#abstract, "
        "div.abstract-group, section[class*='abstract' i], div[class*='abstract' i]"
    ):
        content = host.select_one(".article-section__content") or host
        paras = [_txt(p.get_text(" ", strip=True)) for p in content.find_all("p")]
        paras = [p for p in paras if p]
        if paras:
            return " ".join(paras)

    # 2) Heading “Abstract” (fallback)
    for h in soup.find_all(["h2", "h3", "h4"]):
        title = heading_text(h)
        if re.fullmatch(r"\s*abstract\s*", title or "", re.I):
            nxt = None
            cur = h.next_sibling
            while cur:
                if isinstance(cur, Tag) and cur.name in {"h2", "h3", "h4"}:
                    nxt = cur
                    break
                cur = cur.next_sibling
            paras = paras_between(h, nxt)
            if paras:
                return " ".join(paras)
    return None

def _extract_wiley_keywords(soup: BeautifulSoup) -> List[str]:
    # Prefer structured blocks labeled as keywords/subjects
    for host in soup.find_all(_looks_like_keywords_host):
        items: List[str] = []
        for el in host.select("a, li, span"):
            t = _txt(el.get_text(" ", strip=True))
            if t:
                items.append(t)
        items = [re.sub(r"^\s*Keywords?\s*:\s*", "", t, flags=re.I) for t in items]
        items = [t for t in items if t]
        if items:
            return dedupe_keep_order(items)

    # Fallback inline “Keywords: …”
    m = soup.find(string=re.compile(r"^\s*Keywords?\s*:", re.I))
    if isinstance(m, str):
        tail = re.sub(r"^\s*Keywords?\s*:\s*", "", m, flags=re.I)
        parts = [p.strip() for p in re.split(r"[;,/]|[\r\n]+", tail) if p.strip()]
        if parts:
            return dedupe_keep_order(parts)
    return []

# -------------------------- nested subsection helpers --------------------------

def _is_subsection_container(tag: Tag) -> bool:
    """
    Heuristics to decide if `tag` is a subsection wrapper under a Wiley section.
    Covers classic `.article-section__sub-content` plus accordions/details and common
    "expand/collapse" wrappers used by Wiley templates.
    """
    if not isinstance(tag, Tag):
        return False
    cls = " ".join((tag.get("class") or [])).lower()
    if any(k in cls for k in [
        "article-section__sub-content",     # classic
        "sub-content", "subcontent",        # variants
        "subsection", "section__sub",       # generic
        "accordion", "expand", "collaps",   # accordions/expanders
        "toggle", "disclosure", "tabs"      # misc UI
    ]):
        return True
    if tag.name in {"details"}:
        return True
    # As a last hint, treat blocks that clearly own a subsection heading as containers.
    # (We *don't* use recursive=False here, headings might sit one level down.)
    if tag.find(["h3", "h4", "h5", "h6"]):
        return True
    return False

def _has_subsection_ancestor(el: Tag, root: Tag) -> bool:
    """
    True if `el` has an ancestor between itself and `root` that is a subsection container.
    """
    cur = el.parent
    while isinstance(cur, Tag) and cur is not root:
        if _is_subsection_container(cur):
            return True
        cur = cur.parent
    return False

def _collect_paras_for_section(root: Tag) -> List[str]:
    """
    Collect <p>/<li> that belong to this section, skipping anything inside subsection containers.
    If nothing is found and there are no subsection containers at all, fall back to subtree text.
    """
    return collect_paras_excluding(root, _is_subsection_container)


def _parse_subsection_block(block: Tag) -> Optional[Dict[str, object]]:
    """
    Parse a subsection container into {title, paragraphs, children?}.
    """
    # Subsection heading: prefer h3/h4, then any heading
    h = block.find(["h3", "h4", "h5", "h6"]) or block.find(["h2"])
    title = heading_text(h) if h else ""
    if not title or _NONCONTENT_RX.search(title):
        # Even without a title, we might still have paragraphs; keep it only if we get text
        title = title or ""

    paras = _collect_paras_for_section(block)

    # Recurse: immediate child subsection containers
    kids: List[Dict[str, object]] = []
    for child in block.find_all(True, recursive=False):
        if _is_subsection_container(child):
            node = _parse_subsection_block(child)
            if node and (node.get("title") or node.get("paragraphs") or node.get("children")):
                kids.append(node)
    node: Dict[str, object] = {}
    if title:
        node["title"] = title
    if paras:
        node["paragraphs"] = paras
    if kids:
        node["children"] = kids
    return node if (node.get("title") or node.get("paragraphs") or node.get("children")) else None

# -------------------------- sections extractors --------------------------

def _extract_wiley_sections_structured(wrapper: Tag) -> List[Dict[str, object]]:
    """
    Primary path: structured pages with <section class="article-section__content"> blocks.
    """
    top_secs = wrapper.select("section.article-section__content")
    if not top_secs:
        # Some pages use <div class="article-section__content">
        top_secs = [
            d for d in wrapper.select("div.article-section__content")
            if not (d.find_parent("section", class_=re.compile(r"article-section__abstract", re.I)))
        ]

    out: List[Dict[str, object]] = []
    for sec in top_secs:
        # Section title (h2 usually)
        h = sec.find(["h2", "h3", "h4"])
        title = heading_text(h)
        if not title or re.fullmatch(r"\s*abstract\s*", title, re.I) or _NONCONTENT_RX.search(title):
            continue

        node: Dict[str, object] = {"title": title}

        # Paragraphs that belong to THIS section (exclude nested subsection containers)
        paras = _collect_paras_for_section(sec)
        if paras:
            node["paragraphs"] = paras

        # Children: immediate subsection containers under this section
        children: List[Dict[str, object]] = []
        for child in sec.find_all(True, recursive=False):
            if _is_subsection_container(child):
                kid = _parse_subsection_block(child)
                if kid and (kid.get("title") or kid.get("paragraphs") or kid.get("children")):
                    children.append(kid)
        if children:
            node["children"] = children

        if node.get("title") or node.get("paragraphs") or node.get("children"):
            out.append(node)

    return dedupe_section_nodes(out)

def _extract_wiley_sections_heading_runs(wrapper: Tag) -> List[Dict[str, object]]:
    """
    Fallback: segment by runs of H2.article-section__title, respecting nested subsections.
    """
    out: List[Dict[str, object]] = []
    headings = wrapper.select("h2.article-section__title, h2[class*='article-section__title' i]")
    if not headings:
        return out

    def next_h2(node: Tag) -> Optional[Tag]:
        cur = node.next_sibling
        while cur:
            if isinstance(cur, Tag) and cur.name == "h2" and ("article-section__title" in " ".join(cur.get("class") or []).lower()):
                return cur
            cur = cur.next_sibling
        return None

    for h in headings:
        title = heading_text(h)
        if not title or re.fullmatch(r"\s*abstract\s*", title, re.I) or _NONCONTENT_RX.search(title):
            continue

        end = next_h2(h)
        container = BeautifulSoup("<div></div>", "html.parser").div  # temp container
        cur = h.next_sibling
        while cur and cur is not end:
            if isinstance(cur, Tag):
                container.append(cur.extract())
            cur = h.next_sibling  # after extract, h.next_sibling updates

        node: Dict[str, object] = {"title": title}
        # Paragraphs for this H2 block, excluding nested subsection containers
        paras = _collect_paras_for_section(container)
        if paras:
            node["paragraphs"] = paras

        # Children: immediate subsection containers within this H2 block
        children: List[Dict[str, object]] = []
        for child in container.find_all(True, recursive=False):
            if _is_subsection_container(child):
                kid = _parse_subsection_block(child)
                if kid and (kid.get("title") or kid.get("paragraphs") or kid.get("children")):
                    children.append(kid)
        if children:
            node["children"] = children

        if node.get("title") or node.get("paragraphs") or node.get("children"):
            out.append(node)

    return dedupe_section_nodes(out)


def _extract_wiley_sections(soup: BeautifulSoup) -> List[Dict[str, object]]:
    """
    Return a list of sections with possible children. Prefer structured blocks; fall back to
    heading-run segmentation. Both paths respect nested subsections (accordions/details).
    """
    wrapper = _find_main_wrapper(soup)

    # 1) Try structured content blocks first
    secs = _extract_wiley_sections_structured(wrapper)
    if secs:
        return secs

    # 2) Fallback to heading-run segmentation
    secs = _extract_wiley_sections_heading_runs(wrapper)
    if secs:
        return secs

    return []

def extract_wiley_meta(_url: str, dom_html: str) -> Dict[str, object]:
    """
    Return {"abstract": str|None, "keywords": [str], "sections": [ {title, paragraphs, children?} ]}
    so robust_parse() can populate the reduced view and your UI can build crumbs.
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    abstract = _extract_wiley_abstract(soup)
    keywords = _extract_wiley_keywords(soup)
    sections = _extract_wiley_sections(soup)
    return {"abstract": abstract, "keywords": keywords, "sections": sections}

# -------------------------- registrations --------------------------

# References (host + common proxy)
register(r"(?:^|\.)onlinelibrary\.wiley\.com$", parse_wiley, where="host", name="Wiley Online Library")
register(r"onlinelibrary[-\.]wiley",           parse_wiley, where="url",  name="Wiley (proxy)")

# Meta/sections (host + common proxy)
register_meta(r"(?:^|\.)onlinelibrary\.wiley\.com$", extract_wiley_meta, where="host", name="Wiley meta")
register_meta(r"onlinelibrary[-\.]wiley",             extract_wiley_meta, where="url",  name="Wiley meta (proxy)")
