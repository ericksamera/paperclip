# services/server/captures/site_parsers/sciencedirect.py
from __future__ import annotations
from typing import Dict, List
import re
from bs4 import BeautifulSoup

from . import register
from .base import DOI_RE, YEAR_RE, collapse_spaces, norm, tokenize_authors_csv, authors_initials_first_to_surname_initials

def parse_sciencedirect(url: str, dom_html: str) -> List[Dict[str, object]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    refs: List[Dict[str, object]] = []
    for ref in soup.select("span.reference, div.reference"):
        item: Dict[str, object] = {"raw": collapse_spaces(ref.get_text(" ", strip=True))}
        a_node = ref.select_one(".authors")
        if a_node:
            auths_raw = tokenize_authors_csv(collapse_spaces(a_node.get_text(" ", strip=True)))
            item["authors"] = authors_initials_first_to_surname_initials(auths_raw)
        t_node = ref.select_one(".title")
        if t_node:
            item["title"] = collapse_spaces(t_node.get_text(" ", strip=True))
        h_node = ref.select_one(".host")
        if h_node:
            host = collapse_spaces(h_node.get_text(" ", strip=True))
            m = re.search(r"^(?P<journal>.+?),\s*(?P<vol>\d+)\s*\((?P<year>\d{4})\)", host)
            if m:
                item["container_title"] = collapse_spaces(m.group("journal"))
                item["volume"] = m.group("vol")
                item["issued_year"] = m.group("year")
            mp = re.search(r"pp\.\s*([\d\-–]+)", host) or re.search(r":\s*([\d\-–]+)", host)
            if mp: item["pages"] = mp.group(1)
        doi = ""
        for a in ref.select(".ReferenceLinks a[href]"):
            m = DOI_RE.search(a.get("href", ""))
            if m: doi = m.group(0); break
        item["doi"] = doi
        if not item.get("issued_year"):
            my = YEAR_RE.search(item["raw"])  # type: ignore[index]
            if my: item["issued_year"] = my.group(0)
        for k in ("doi","title","container_title","volume","issued_year","pages"):
            item[k] = norm(item.get(k))  # type: ignore[index]
        refs.append(item)
    return refs

# Register: host suffix match
register(r"(?:^|\.)sciencedirect\.com$", parse_sciencedirect, where="host", name="ScienceDirect")
