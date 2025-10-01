from __future__ import annotations
import html
import re
from typing import Dict, Optional, Tuple, List

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE  = re.compile(r"[ \t\r\f\v]+")
_NBSP   = "\u00A0"

def _strip_tags(s: str) -> str:
    s = _TAG_RE.sub(" ", s or "")
    s = html.unescape(s)
    s = s.replace(_NBSP, " ")
    s = _WS_RE.sub(" ", s)
    return s.strip()

def _find_meta(content: str, names: Tuple[str, ...]) -> Optional[str]:
    """Return the first <meta name|property=NAME content=...> match."""
    if not content:
        return None
    for n in names:
        # name=
        m = re.search(
            rf'<meta[^>]*\bname=["\']{re.escape(n)}["\'][^>]*\bcontent=["\']([^"\']+)["\']',
            content, re.I
        )
        if m:
            return html.unescape(m.group(1)).strip()
        # property=
        m = re.search(
            rf'<meta[^>]*\bproperty=["\']{re.escape(n)}["\'][^>]*\bcontent=["\']([^"\']+)["\']',
            content, re.I
        )
        if m:
            return html.unescape(m.group(1)).strip()
    return None

def _title_from_dom(dom_html: str) -> Optional[str]:
    if not dom_html: return None
    m = re.search(r"<title[^>]*>(.*?)</title>", dom_html, re.I | re.S)
    return html.unescape(m.group(1)).strip() if m else None

# ---------- content helpers ----------

_P_PATT = re.compile(r"<p\b[^>]*>(.*?)</p>", re.I | re.S)

def _paragraphs_from_html(fragment: str) -> List[str]:
    """Pull ordered <p>…</p> texts from a fragment; fall back to one big block if needed."""
    if not fragment:
        return []
    paras = []
    for m in _P_PATT.findall(fragment):
        t = _strip_tags(m)
        if t and len(t) > 1:
            paras.append(t)
    if paras:
        return paras
    # fallback: strip all tags and try to split on sentence-ish breaks
    raw = _strip_tags(fragment)
    out = [p.strip() for p in re.split(r"\n{2,}|\.\s+(?=[A-Z])", raw) if p.strip()]
    return out[:8]

def _segment_from_dom(dom_html: str) -> str:
    if not dom_html:
        return ""
    # Prefer <main>…</main>
    m = re.search(r"<main\b[^>]*>(.*?)</main>", dom_html, re.I | re.S)
    if m:
        return m.group(1)
    # Then <article>…</article>
    m = re.search(r"<article\b[^>]*>(.*?)</article>", dom_html, re.I | re.S)
    if m:
        return m.group(1)
    # Else whole <body>
    m = re.search(r"<body\b[^>]*>(.*?)</body>", dom_html, re.I | re.S)
    return m.group(1) if m else dom_html

def _extract_abstract(dom_html: str) -> Optional[str]:
    if not dom_html:
        return None
    # 1) explicit abstract containers
    m = re.search(r'<(section|div)[^>]*class="[^"]*abstract[^"]*"[^>]*>(.*?)</\1>', dom_html, re.I | re.S)
    if m:
        txt = _strip_tags(m.group(2))
        return txt or None
    # 2) heading “Abstract” until next heading
    h = re.search(r"<h\d[^>]*>\s*Abstract\s*</h\d>\s*(.+?)(?:<h\d|\Z)", dom_html, re.I | re.S)
    if h:
        txt = _strip_tags(h.group(1))
        return txt or None
    return None

# ---------- head-meta helpers ----------

def _split_keywords(v: str) -> List[str]:
    parts = [p.strip() for p in re.split(r"[;,/]", v or "") if p.strip()]
    # dedupe (case-insensitive) in-order
    seen, out = set(), []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k); out.append(p)
    return out

def _parse_authors(dom_html: str) -> List[str]:
    # Multiple <meta name="citation_author" content="...">
    out: List[str] = []
    for m in re.finditer(r'<meta[^>]*\bname=["\']citation_author["\'][^>]*\bcontent=["\']([^"\']+)["\']', dom_html or "", re.I):
        a = html.unescape(m.group(1)).strip()
        if a:
            out.append(a)
    # <meta name="dc.creator" content="A; B; C">
    m = re.search(r'<meta[^>]*\bname=["\']dc\.creator["\'][^>]*\bcontent=["\']([^"\']+)["\']', dom_html or "", re.I)
    if m:
        tail = html.unescape(m.group(1))
        out.extend([p.strip() for p in tail.split(";") if p.strip()])
    # de-dup in-order
    seen, uniq = set(), []
    for a in out:
        k = a.lower()
        if k not in seen:
            seen.add(k); uniq.append(a)
    return uniq

# ---------- public fallback ----------

def fallbacks(url: str | None, dom_html: str, content_html: str) -> Dict[str, object]:
    """
    Return {"meta_updates": {...}, "content_sections": {...}} using generic heuristics only.
    - meta_updates includes: title, doi, issued_year (int), container_title, url, keywords (list), authors (list)
    - content_sections includes: abstract_or_body (list[str]), abstract (optional str)
    """
    title = (
        _find_meta(dom_html, ("citation_title", "dc.title", "DC.Title", "og:title"))
        or _title_from_dom(dom_html)
        or ""
    )
    doi = _find_meta(dom_html, ("citation_doi", "dc.identifier", "dc.identifier.doi", "prism.doi")) or ""

    pubdate = _find_meta(dom_html, ("citation_publication_date", "prism.publicationdate", "dc.date", "dcterms.issued")) or ""
    issued_year: Optional[int] = None
    if pubdate:
        m = re.search(r"\b(19|20)\d{2}\b", pubdate)
        if m:
            try:
                issued_year = int(m.group(0))
            except Exception:
                issued_year = None

    container = _find_meta(dom_html, ("citation_journal_title", "prism.publicationname")) or ""
    keywords_meta = _find_meta(dom_html, ("citation_keywords", "keywords", "dc.subject")) or ""
    keywords = _split_keywords(keywords_meta) if keywords_meta else []

    authors = _parse_authors(dom_html)

    # Paragraphs for preview
    abs_txt = _extract_abstract(dom_html) or ""
    if content_html:
        paras = _paragraphs_from_html(content_html)
    else:
        segment = _segment_from_dom(dom_html)
        # strip scripts/styles out of segment first
        segment = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", segment, flags=re.I | re.S)
        paras = _paragraphs_from_html(segment)

    meta_updates: Dict[str, object] = {}
    if title: meta_updates["title"] = title
    if doi: meta_updates["doi"] = doi
    if issued_year is not None: meta_updates["issued_year"] = issued_year
    if container: meta_updates["container_title"] = container
    if url: meta_updates["url"] = url
    if keywords: meta_updates["keywords"] = keywords
    if authors: meta_updates["authors"] = authors

    return {
        "meta_updates": meta_updates,
        "content_sections": {
            "abstract_or_body": paras,
            "abstract": abs_txt,
        },
    }
