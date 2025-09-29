from __future__ import annotations
from bs4 import BeautifulSoup
import re
from typing import Dict, Any

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)

def _pick(soup, names):
    for n in names:
        el = soup.find("meta", attrs={"name": n}) or soup.find("meta", attrs={"property": n})
        if el and el.get("content"):
            return el["content"].strip()
    return None

def _year_from(s: str | None):
    if not s:
        return None
    # accept YYYY, or any date that contains a YYYY like 2022/09/05, 2022-09, 2022.09.05, etc.
    m = re.search(r"(19|20)\d{2}", s)
    return int(m.group(0)) if m else None

def extract_head_meta(dom_html: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not dom_html:
        return out
    soup = BeautifulSoup(dom_html, "html.parser")

    title = _pick(soup, [
        "citation_title","dc.title","dcterms.title","prism.title"
    ]) or (soup.title.get_text(strip=True) if soup.title else None)
    if title:
        out["title"] = title
        out["title_source"] = "citation"  # best effort

    doi = _pick(soup, ["citation_doi","prism.doi","dc.identifier","dcterms.identifier"])
    if not doi:
        # try any DOI-like in meta content
        metas = " ".join(m.get("content","") for m in soup.find_all("meta"))
        m = DOI_RE.search(metas)
        if m: doi = m.group(0)
    if doi:
        out["doi"] = doi

    year = _year_from(_pick(soup, [
        "citation_publication_date",
        "citation_date",
        "prism.publicationdate",
        "dc.date",
        "dcterms.issued",
    ]))
    if year:
        out["issued_year"] = year

    return out
