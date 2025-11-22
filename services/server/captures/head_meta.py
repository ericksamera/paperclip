from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from paperclip.utils import norm_doi

DOI_RE = re.compile(r"10\.\d{1,9}/[^\s\"'<>]+", re.I)


def _pick(soup: BeautifulSoup, names: list[str]) -> str | None:
    for n in names:
        el = soup.find("meta", attrs={"name": n}) or soup.find(
            "meta", attrs={"property": n}
        )
        if el and el.get("content"):
            return el["content"].strip()
    return None


def _year_from(s: str | None) -> int | None:
    if not s:
        return None
    m = re.search(r"(19|20)\d{2}", s)
    return int(m.group(0)) if m else None


def extract_head_meta(dom_html: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not dom_html:
        return out

    soup = BeautifulSoup(dom_html, "html.parser")

    # Title
    title = _pick(
        soup, ["citation_title", "dc.title", "dcterms.title", "prism.title"]
    ) or (soup.title.get_text(strip=True) if soup.title else None)
    if title:
        out["title"] = title
        out["title_source"] = "citation"  # best effort

    # DOI (normalized)
    doi_raw = _pick(
        soup, ["citation_doi", "prism.doi", "dc.identifier", "dcterms.identifier"]
    )
    if not doi_raw:
        # try any DOI-like in meta content
        metas = " ".join(m.get("content", "") for m in soup.find_all("meta"))
        m = DOI_RE.search(metas)
        if m:
            doi_raw = m.group(0)

    if doi_raw:
        doi_norm = norm_doi(doi_raw)
        out["doi"] = doi_norm or doi_raw.strip()

    # Year
    year = _year_from(
        _pick(
            soup,
            [
                "citation_publication_date",
                "citation_date",
                "prism.publicationdate",
                "dc.date",
                "dcterms.issued",
            ],
        )
    )
    if year:
        out["issued_year"] = year

    return out
