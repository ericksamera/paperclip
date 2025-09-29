# services/server/captures/site_parsers/wiley.py
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup, Tag

from . import register

DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>),;]+", re.I)


# -------------------------- utilities --------------------------

def norm_space(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def normalize_dash(s: str) -> str:
    s = s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    s = re.sub(r"\s*-\s*", "-", s)
    return s.strip(" -\t")


def take_text(node: Tag | None) -> str:
    return norm_space(node.get_text(" ", strip=True)) if node else ""


def is_icon_i(tag: Tag) -> bool:
    if not isinstance(tag, Tag) or tag.name != "i":
        return False
    classes = tag.get("class") or []
    return any("icon" in (c or "") for c in classes)


def clean_doi(raw: str | None) -> Optional[str]:
    if not raw:
        return None
    x = raw.strip()
    x = re.sub(r"(?i)^\s*doi:\s*", "", x)
    x = re.sub(r"(?i)^https?://(?:dx\.)?doi\.org/", "", x)
    x = x.strip().strip(".,;)]}")
    return x.lower() or None


# -------------------------- field extraction --------------------------

def extract_doi(li: Tag) -> Optional[str]:
    # 1) hidden span
    doi_span = li.find("span", class_=lambda c: c and "data-doi" in c)
    if doi_span:
        d = clean_doi(take_text(doi_span))
        if d:
            return d

    # 2) DOI-looking <a class=accessionId> text or href
    acc = li.find("a", class_=lambda c: c and "accessionId" in c)
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


# -------------------------- LI → reference dict --------------------------

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


# -------------------------- selectors & parser --------------------------

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


def parse_wiley(url: str, dom_html: str) -> List[Dict[str, object]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: List[Dict[str, object]] = []
    for li in _select_reference_items(soup):
        ref = parse_one_li(li)
        if ref:
            out.append(ref)
    return out


# Register for Wiley (normal host) and common proxy URL patterns.
register(r"(?:^|\.)onlinelibrary\.wiley\.com$", parse_wiley, where="host", name="Wiley Online Library")
register(r"onlinelibrary[-\.]wiley", parse_wiley, where="url", name="Wiley (proxy)")
