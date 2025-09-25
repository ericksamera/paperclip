# captures/head_meta.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import re
from datetime import datetime
from bs4 import BeautifulSoup

_DOI_RE = re.compile(r'(10\.\d{4,9}/[^\s"<>]+)', re.I)

def _norm(s: Optional[str]) -> str:
    return (s or "").strip()

def _strip_doi_prefix(s: str) -> str:
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', "", s, flags=re.I).strip()

def _parse_pubdate_to_iso_and_year(raw: str) -> Tuple[Optional[str], Optional[int]]:
    raw = raw.strip()
    fmts = [
        "%Y-%m-%d", "%Y/%m/%d",
        "%Y %b %d", "%Y %B %d",
        "%b %d, %Y", "%B %d, %Y",
        "%d %b %Y", "%d %B %Y",
        "%Y-%m", "%Y/%m", "%Y %b", "%Y %B",
        "%Y",
    ]
    for f in fmts:
        try:
            dt = datetime.strptime(raw, f)
            y = dt.year
            iso = f in ("%Y",) and None or dt.date().isoformat()
            if f in ("%Y-%m", "%Y/%m", "%Y %b", "%Y %B"):
                iso = f"{y:04d}-{dt.month:02d}-01"
            return iso, y
        except Exception:
            pass
    m = re.search(r'(19|20)\d{2}', raw)
    return None, int(m.group(0)) if m else None

# Trim typical site suffixes only for og/html fallbacks
_SUFFIX_RE = re.compile(
    r"""\s*(?:[|–—-])\s*
        (Wiley\s+Online\s+Library|SpringerLink|ScienceDirect|Taylor\s*&\s*Francis\s*Online|
         Nature|PLOS(?:\s+ONE)?|PMC|PubMed\s+Central|MDPI|BMC|Elsevier.*|SAGE\s*Journals)
        .*$
    """,
    re.I | re.X,
)
def _clean_title(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return _SUFFIX_RE.sub("", s)

def extract_head_meta(dom_html: str | None) -> Dict[str, Any]:
    """
    Return a small dict from <head>, including:
      - doi
      - title     (best available)
      - title_source  ('citation'|'dc'|'og'|'html')
      - container_title/journal
      - issued_year/published
      - keywords (if present)
    """
    if not dom_html:
        return {}

    soup = BeautifulSoup(dom_html, "html.parser")
    updates: Dict[str, Any] = {}

    def meta_first(*names: str) -> Optional[str]:
        for nm in names:
            m = soup.find("meta", attrs={"name": re.compile(rf"^{re.escape(nm)}$", re.I)})
            if m and m.get("content"):
                return _norm(m["content"])
        return None

    # DOI
    doi = meta_first("citation_doi", "prism.doi", "dc.identifier", "doi")
    if doi:
        doi = _strip_doi_prefix(doi)
        m = _DOI_RE.search(doi)
        updates["doi"] = m.group(1) if m else doi
    else:
        head = soup.head or soup
        a = head.select_one('a[href*="doi.org/"]')
        if a and a.get("href"):
            m = _DOI_RE.search(a["href"])
            if m:
                updates["doi"] = m.group(1)
        else:
            text = head.get_text(" ", strip=True) if head else ""
            m = _DOI_RE.search(text)
            if m:
                updates["doi"] = m.group(1)

    # Title with source
    title, src = None, None
    t = meta_first("citation_title", "dc.title", "dcterms.title", "prism.title")
    if t:
        title = t
        src = "citation" if soup.find("meta", attrs={"name": re.compile("^citation_title$", re.I)}) else "dc"
    else:
        og = soup.find("meta", attrs={"property": re.compile("^og:title$", re.I)})
        if og and og.get("content"):
            title = _norm(og["content"])
            src = "og"
    if not title and soup.title and soup.title.string:
        title = _norm(soup.title.string)
        src = "html"
    if title:
        if src in ("og", "html"):
            title = _clean_title(title)
        updates["title"] = title
        updates["title_source"] = src

    # Journal
    journal = meta_first("citation_journal_title", "prism.publicationname", "journal")
    if journal:
        updates["container_title"] = journal
        updates["journal"] = journal

    # Publication date & year
    pub = meta_first("citation_publication_date", "prism.publicationdate", "dc.date", "dcterms.issued")
    if pub:
        iso, year = _parse_pubdate_to_iso_and_year(pub)
        if iso:
            updates["published"] = iso
        if year:
            updates["issued_year"] = year
    else:
        y = meta_first("citation_year")
        if y:
            try: updates["issued_year"] = int(y.strip())
            except Exception: pass

    # Keywords
    kw = meta_first("citation_keywords", "keywords")
    if kw:
        toks = [p.strip() for p in kw.replace(";", ",").split(",") if p.strip()]
        if toks:
            updates["keywords"] = toks

    return updates
