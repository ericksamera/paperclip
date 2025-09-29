# services/server/captures/site_parsers/pmc.py
from __future__ import annotations
from typing import Dict, List
from bs4 import BeautifulSoup

from . import register
from .base import extract_from_li, augment_from_raw

def parse_pmc(url: str, dom_html: str) -> List[Dict[str, object]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    refs: List[Dict[str, object]] = []

    for li in soup.select("section.ref-list li, .ref-list li, ol.ref-list li, ul.ref-list li"):
        if not li.get_text(strip=True):
            continue
        base = extract_from_li(li)
        refs.append(augment_from_raw(base))

    if not refs:
        for li in soup.select("ol.references li, ul.references li"):
            if not li.get_text(strip=True):
                continue
            base = extract_from_li(li)
            refs.append(augment_from_raw(base))
    return refs

# Route by host AND by url path
register(r"(?:^|\.)pmc\.ncbi\.nlm\.nih\.gov$", parse_pmc, where="host", name="PMC host")
register(r"ncbi\.nlm\.nih\.gov/.*/pmc/|/pmc/", parse_pmc, where="url",  name="PMC path")
