from __future__ import annotations
from typing import Any, Dict

from .sections_fallbacks import fallbacks as _fallbacks
from captures.head_meta import extract_head_meta
from captures.site_parsers import extract_sections_meta  # site-aware meta/sections (best-effort)

def robust_parse(*, url: str | None, content_html: str, dom_html: str) -> Dict[str, Any]:
    """
    Compose strong meta + site-specific sections + generic fallbacks into one shape.
    This version avoids a BeautifulSoup pass for <head> unless needed.
    """
    # 1) Generic fallbacks (regex-based; cheap) → meta + preview paragraphs
    fb = _fallbacks(url, dom_html or "", content_html or "")
    fb_meta = dict(fb.get("meta_updates") or {})
    fb_secs = dict(fb.get("content_sections") or {})

    # 2) Site-specific sections/keywords (one soup parse inside)
    site = extract_sections_meta(url, dom_html or "") or {}

    # 3) Merge meta — only call extract_head_meta (soup) if a core field is missing
    mu: Dict[str, Any] = {}
    mu.update({k: v for k, v in fb_meta.items() if k not in {"title", "doi", "issued_year"}})
    if url and not mu.get("url"):
        mu["url"] = url

    strong = None  # lazy
    def _need_strong():
        nonlocal strong
        if strong is None:
            strong = extract_head_meta(dom_html or "") or {}

    for key in ("title", "doi", "issued_year"):
        if fb_meta.get(key) is not None:
            mu[key] = fb_meta[key]
        else:
            _need_strong()
            if strong.get(key) is not None:
                mu[key] = strong[key]

    # 4) Sections payload
    sections: Dict[str, Any] = {"abstract_or_body": list(fb_secs.get("abstract_or_body") or [])}
    if site.get("abstract"):
        sections["abstract"] = site["abstract"]
    elif fb_secs.get("abstract"):
        sections["abstract"] = fb_secs["abstract"]
    if site.get("sections"):
        sections["sections"] = site["sections"]

    return {"meta_updates": mu, "content_sections": sections}