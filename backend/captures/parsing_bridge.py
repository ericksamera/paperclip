# services/server/captures/parsing_bridge.py
from __future__ import annotations

from typing import Any

from captures.head_meta import extract_head_meta
from captures.site_parsers import (
    extract_sections_meta,
)  # site-aware meta/sections (best-effort)

from .sections_fallbacks import fallbacks as _fallbacks


def _merge_keywords(*sources: object) -> list[str]:
    """
    Merge keyword sources (lists/tuples/sets/strings), dedupe case-insensitively,
    preserve order, and return a clean list[str].
    """
    out: list[str] = []
    seen: set[str] = set()
    for src in sources:
        if src is None:
            continue
        if isinstance(src, str):
            items = [src]
        elif isinstance(src, list | tuple | set):
            items = [str(x) for x in src]
        else:
            continue
        for k in items:
            t = str(k).strip()
            if not t:
                continue
            lk = t.lower()
            if lk in seen:
                continue
            seen.add(lk)
            out.append(t)
    return out


def robust_parse(
    *, url: str | None, content_html: str, dom_html: str
) -> dict[str, Any]:
    """
    Compose strong meta + site-specific sections + generic fallbacks into one shape.
    This version avoids a BeautifulSoup pass for <head> unless needed.
    """
    # 1) Generic fallbacks (regex-based; cheap) → meta + preview paragraphs
    fb: dict[str, Any] = _fallbacks(url, dom_html or "", content_html or "")
    mu_raw = fb.get("meta_updates")
    sec_raw = fb.get("content_sections")

    # Guard types so mypy knows these are dicts (no dict(object) calls)
    fb_meta: dict[str, Any] = mu_raw if isinstance(mu_raw, dict) else {}
    fb_secs: dict[str, Any] = sec_raw if isinstance(sec_raw, dict) else {}

    # 2) Site-specific sections/keywords (one soup parse inside)
    site_raw = extract_sections_meta(url, dom_html or "") or {}
    site: dict[str, Any] = site_raw if isinstance(site_raw, dict) else {}

    # 3) Merge meta - only call extract_head_meta (soup) if a core field is missing
    mu: dict[str, Any] = {}
    mu.update(
        {k: v for k, v in fb_meta.items() if k not in {"title", "doi", "issued_year"}}
    )
    if url and not mu.get("url"):
        mu["url"] = url

    strong_loaded = False
    strong: dict[str, Any] = {}

    for key in ("title", "doi", "issued_year"):
        if fb_meta.get(key) is not None:
            mu[key] = fb_meta[key]
        else:
            if not strong_loaded:
                tmp = extract_head_meta(dom_html or "")
                strong = tmp if isinstance(tmp, dict) else {}
                strong_loaded = True
            if key in strong and strong[key] is not None:
                mu[key] = strong[key]

    # Merge site keywords into meta (prefer site, keep fallbacks; preserve order and dedupe).
    try:
        merged_kw = _merge_keywords(fb_meta.get("keywords"), site.get("keywords"))
        if merged_kw:
            mu["keywords"] = merged_kw
    except Exception:
        # Never break ingest on keywords
        pass

    # 4) Sections payload
    sections: dict[str, Any] = {}

    aob = fb_secs.get("abstract_or_body")
    if isinstance(aob, list):
        sections["abstract_or_body"] = [str(x) for x in aob]
    elif isinstance(aob, str) and aob:
        sections["abstract_or_body"] = [aob]
    else:
        sections["abstract_or_body"] = []

    abs_site = site.get("abstract")
    abs_fb = fb_secs.get("abstract")
    if isinstance(abs_site, str) and abs_site:
        sections["abstract"] = abs_site
    elif isinstance(abs_fb, str) and abs_fb:
        sections["abstract"] = abs_fb

    site_sections = site.get("sections")
    if isinstance(site_sections, list):
        sections["sections"] = site_sections

    return {"meta_updates": mu, "content_sections": sections}
