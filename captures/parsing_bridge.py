# captures/parsing_bridge.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple
from bs4 import BeautifulSoup
from .head_meta import extract_head_meta

def _heuristic_parse(url: str, content_html: str | None, dom_html: str | None) -> Dict[str, Any]:
    """
    Very light fallback: extract abstract and simple section bodies where available.
    """
    html = content_html or dom_html or ""
    soup = BeautifulSoup(html, "html.parser")

    # Abstract
    abstract_blocks: List[Dict[str, Any]] = []
    for sel in ("section.abstract", "div.abstract", "section#abstract", "div#abstract"):
        node = soup.select_one(sel)
        if node:
            text = " ".join(node.get_text(" ", strip=True).split())
            if text:
                abstract_blocks = [{"title": None, "body": text}]
                break

    # Keywords – we prefer head_meta when present, but sometimes body has a list
    body_keywords: List[str] = []
    for li in soup.select("ul.keywords li, .keywords li"):
        t = li.get_text(" ", strip=True)
        if t and t not in body_keywords:
            body_keywords.append(t)

    # Body: top-level sections (best-effort)
    body_sections: List[Dict[str, Any]] = []
    for sec in soup.select("section[id], div.article-body section"):
        h = None
        for tag in ("h1","h2","h3"):  # keep light
            h = sec.find(tag)
            if h: break
        if not h:
            continue
        title = h.get_text(" ", strip=True)
        paras = [p.get_text(" ", strip=True) for p in sec.find_all("p", recursive=False)]
        paras = [t for t in paras if t.strip()]
        if title or paras:
            body_sections.append({"title": title, "paragraphs": [{"markdown": t} for t in paras]})

    return {
        "content_sections": {
            "abstract": abstract_blocks,
            "body": body_sections,
            "keywords": body_keywords,
        }
    }


def robust_parse(url: str, content_html: str | None, dom_html: str | None) -> Dict[str, Any]:
    """
    Combine head-meta extraction (DOI, journal, pub date, year) with a minimal body parser.
    """
    head = extract_head_meta(dom_html)
    body = _heuristic_parse(url, content_html, dom_html)
    # Merge keywords (union), prefer head ones
    kws = list(dict.fromkeys((head.get("keywords") or []) + (body["content_sections"].get("keywords") or [])))
    meta_updates = dict(head)
    if kws:
        meta_updates["keywords"] = kws
    return {
        "meta_updates": meta_updates,
        **body
    }
