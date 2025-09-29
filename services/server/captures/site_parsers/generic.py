# services/server/captures/site_parsers/generic.py
from __future__ import annotations
from typing import Dict, List
from bs4 import BeautifulSoup

from .base import extract_from_li, augment_from_raw

def parse_generic(_url: str, dom_html: str) -> List[Dict[str, object]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    refs: List[Dict[str, object]] = []
    selectors = [
        "ol.references li", "ul.references li",
        "ol.cited-references li", "ul.cited-references li",
        "section.references li", "section#references li",
        "li[id^='ref'], li[id^='B'], li[id^='R']",
    ]
    for sel in selectors:
        for li in soup.select(sel):
            if not li.get_text(strip=True): continue
            base = extract_from_li(li)
            refs.append(augment_from_raw(base))
        if refs: break
    return refs
