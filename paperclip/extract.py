from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .textutil import as_str

_DOI_RX = re.compile(r"10\.\d{4,9}/[^\s<>\"']+", re.I)
_YEAR_RX = re.compile(r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b")


def parse_head_meta(dom_html: str) -> tuple[dict[str, Any], str]:
    """
    Returns: (meta_dict, title_tag_text)
    meta_dict keys are lowercased.
    Values are either str or list[str] for repeated keys.
    """
    if not dom_html:
        return {}, ""

    soup = BeautifulSoup(dom_html, "html.parser")
    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""

    found: dict[str, Any] = {}
    for m in soup.select("meta[name],meta[property]"):
        k = (m.get("name") or m.get("property") or "").strip().lower()
        if not k:
            continue
        v = (m.get("content") or "").strip()
        if not v:
            continue

        # Preserve repeats (e.g., citation_author can be repeated)
        if k in found:
            if isinstance(found[k], list):
                found[k].append(v)
            else:
                found[k] = [found[k], v]
        else:
            found[k] = v

    return found, title_text


def normalize_doi(raw: Any) -> str:
    s = as_str(raw).strip()
    if not s:
        return ""
    s = s.replace("\u200b", "").strip()
    s = re.sub(r"(?i)^\s*https?://(?:dx\.)?doi\.org/", "", s).strip()
    s = re.sub(r"(?i)^\s*doi\s*:\s*", "", s).strip()
    s = s.strip().strip(".,;:)]}\"'")

    m = _DOI_RX.search(s)
    if not m:
        return ""
    return m.group(0).lower()


def extract_year(raw_date: Any) -> int | None:
    s = as_str(raw_date)
    if not s:
        return None
    m = _YEAR_RX.search(s)
    if not m:
        return None
    try:
        y = int(m.group(1))
    except Exception:
        return None
    # sanity range
    if y < 1500 or y > 2200:
        return None
    return y


def split_keywords(raw: Any) -> list[str]:
    s = as_str(raw)
    if not s:
        return []
    # common separators: comma, semicolon, newline
    parts = re.split(r"[,\n;]+", s)
    out: list[str] = []
    seen = set()
    for p in parts:
        k = p.strip()
        if not k:
            continue
        kk = k.lower()
        if kk in seen:
            continue
        seen.add(kk)
        out.append(k)
    return out


def _dedupe_strs(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        s = str(it or "").strip()
        if not s:
            continue
        k = s.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def split_authors(raw: Any) -> list[str]:
    """
    Normalize author metadata into a list of author strings.

    Supports:
      - repeated <meta name="citation_author" ...> => list[str]
      - "citation_authors" (plural) strings, often separated by ';' on PubMed-like pages
      - dc.creator strings, sometimes separated by ';' or newlines
      - minimal support for "A and B" forms

    We intentionally avoid splitting on commas, since many sources use "Last, First".
    """
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        parts: list[str] = []
        for v in raw:
            parts.extend(split_authors(v))
        return _dedupe_strs(parts)

    s = as_str(raw).strip()
    if not s:
        return []

    # Prefer clear separators
    if ";" in s or "\n" in s:
        toks = re.split(r"[;\n]+", s)
    else:
        # Some sources use "A and B"
        if re.search(r"\s+and\s+", s, flags=re.I):
            toks = re.split(r"\s+and\s+", s, flags=re.I)
        else:
            toks = [s]

    return _dedupe_strs([t.strip() for t in toks])


def best_authors(meta: dict[str, Any]) -> list[str]:
    # Order matters: prefer the canonical repeated tag, but accept common variants.
    for k in (
        "citation_author",  # repeated meta tags
        "citation_authors",  # PubMed (often semicolon-separated)
        "dc.creator",
        "dcterms.creator",
    ):
        authors = split_authors(meta.get(k))
        if authors:
            return authors
    return []


def best_abstract(meta: dict[str, Any], *, max_chars: int = 20000) -> str:
    for k in ("citation_abstract", "dcterms.abstract", "dc.description"):
        s = as_str(meta.get(k)).strip()
        if not s:
            continue
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) > max_chars:
            s = s[:max_chars]
        return s
    return ""


def html_to_text(html: str, *, max_chars: int = 400_000) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # Reduce noisy script/style
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def best_title(meta: dict[str, Any], title_tag_text: str, source_url: str) -> str:
    candidates = [
        meta.get("citation_title"),
        meta.get("dc.title"),
        meta.get("dcterms.title"),
        meta.get("prism.title"),
        title_tag_text,
    ]
    for c in candidates:
        s = as_str(c).strip()
        if s:
            return s
    return source_url or "Untitled"


def best_container_title(meta: dict[str, Any]) -> str:
    for k in ("citation_journal_title", "prism.publicationname"):
        s = as_str(meta.get(k)).strip()
        if s:
            return s
    return ""


def best_date(meta: dict[str, Any]) -> str:
    for k in (
        "citation_publication_date",
        "prism.publicationdate",
        "citation_date",
        "dc.date",
        "dcterms.issued",
    ):
        s = as_str(meta.get(k)).strip()
        if s:
            return s
    return ""


def best_doi(meta: dict[str, Any]) -> str:
    for k in ("citation_doi", "prism.doi", "dc.identifier"):
        d = normalize_doi(meta.get(k))
        if d:
            return d
    return ""


def best_keywords(meta: dict[str, Any]) -> list[str]:
    for k in ("citation_keywords", "keywords"):
        ks = split_keywords(meta.get(k))
        if ks:
            return ks
    return []
