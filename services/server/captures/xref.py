# services/server/captures/xref.py
from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
from django.conf import settings

from captures.types import CSL, CSLAuthor
from paperclip.conf import ENRICH_TIMEOUT, USER_AGENT
from paperclip.utils import norm_doi  # central DOI normalization

# NOTE: compute cache dir at access time (reads settings dynamically, easy to override in tests)
_CACHE_DIR: Path = getattr(settings, "DATA_DIR", Path(".")) / "cache" / "crossref"


def _cache_path(doi: str) -> Path:
    key = quote(norm_doi(doi), safe="")
    return _CACHE_DIR / f"{key}.json"


# ---------- in-memory cache ----------
_CACHE_MEM: dict[str, dict] = {}


def _cache_get(doi: str) -> dict | None:
    key = norm_doi(doi)
    if not key:
        return None
    if key in _CACHE_MEM:
        return _CACHE_MEM[key]
    fp = _cache_path(key)
    if fp.exists():
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            _CACHE_MEM[key] = data
            return data
        except Exception:
            return None
    return None


def _cache_put(doi: str, csl: dict) -> None:
    key = norm_doi(doi)
    if not key:
        return
    _CACHE_MEM[key] = csl
    with suppress(Exception):
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_text(json.dumps(csl, ensure_ascii=False), encoding="utf-8")


# ---------- helpers: light normalization into our CSL TypedDict ----------
def _norm_str_or_first(v: Any) -> str:
    if isinstance(v, list):
        for s in v:
            if s:
                return str(s)
        return str(v[0] if v else "")
    return str(v or "")


def _normalize_csl(raw: dict[str, Any]) -> CSL:
    """Return a tiny, normalized CSL dict (keeps only fields we actually use)."""
    authors: List[CSLAuthor] = []
    for a in (raw.get("author") or []):
        if not isinstance(a, dict):
            continue
        fam = str(a.get("family") or a.get("last") or "").strip()
        giv = str(a.get("given") or a.get("first") or "").strip()
        if fam or giv:
            authors.append(CSLAuthor(family=fam, given=giv))

    out: CSL = CSL()
    if authors:
        out["author"] = authors
    if "issued" in raw and isinstance(raw["issued"], dict):
        out["issued"] = raw["issued"]  # contains "date-parts"
    title = _norm_str_or_first(raw.get("title"))
    if title:
        out["title"] = title
    container = _norm_str_or_first(raw.get("container-title"))
    if container:
        out["container_title"] = container
    for k in ("DOI", "page", "volume", "issue", "abstract"):
        v = raw.get(k)
        if v:
            out[k] = str(v)
    return out


def _fetch_csl_for_doi(doi: str) -> Optional[CSL]:
    doi = norm_doi(doi)
    if not doi:
        return None
    cached = _cache_get(doi)
    if cached:
        # tolerate either raw crossref or our normalized shape in cache
        c = cached if "container_title" in cached or "container-title" in cached else cached
        return _normalize_csl(c)  # idempotent if already normalized
    try:
        url = f"https://api.crossref.org/v1/works/{doi}/transform/application/vnd.citationstyles.csl+json"
        r = requests.get(
            url,
            timeout=ENRICH_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.citationstyles.csl+json"},
        )
        if r.ok:
            csl_raw = r.json()
            csl_norm = _normalize_csl(csl_raw)
            _cache_put(doi, csl_norm)
            return csl_norm
    except Exception:
        return None
    return None


# ---------- helpers to format CSL ----------
def _family_given_list(csl: CSL) -> List[CSLAuthor]:
    return [a for a in (csl.get("author") or []) if isinstance(a, dict)]


def _year_from_csl(csl: CSL) -> Optional[str]:
    parts = ((csl.get("issued") or {}).get("date-parts") or []) or []
    if parts and parts[0]:
        y = parts[0][0]
        try:
            return str(int(y))
        except Exception:
            return None
    return None


def _name_abbrev(fam: str, giv: str) -> str:
    initial = (giv[0].upper() + ".") if giv else ""
    return f"{fam}, {initial}".strip().rstrip(",")


def _apa_from_csl(csl: CSL, doi: str) -> str:
    names = _family_given_list(csl)
    if names:
        if len(names) == 1:
            authors = _name_abbrev(names[0].get("family", ""), names[0].get("given", ""))
        elif len(names) == 2:
            a = _name_abbrev(names[0].get("family", ""), names[0].get("given", ""))
            b = _name_abbrev(names[1].get("family", ""), names[1].get("given", ""))
            authors = f"{a}, & {b}"
        else:
            a = _name_abbrev(names[0].get("family", ""), names[0].get("given", ""))
            authors = f"{a} et al."
    else:
        authors = ""

    year = _year_from_csl(csl) or ""
    title = _norm_str_or_first(csl.get("title"))
    journal = _norm_str_or_first(csl.get("container_title"))
    volume = str(csl.get("volume") or "")
    issue = str(csl.get("issue") or "")
    pages = str(csl.get("page") or "")
    doi_url = f"https://doi.org/{quote(doi)}" if doi else ""

    parts: List[str] = []
    if authors:
        parts.append(f"{authors}.")
    if year:
        parts.append(f"({year}).")
    if title:
        parts.append(f"{title}.")
    if journal:
        parts.append(journal)
    tail_bits: List[str] = []
    if volume:
        tail_bits.append(volume)
    if issue:
        tail_bits.append(f"({issue})")
    if pages:
        tail_bits.append(pages)
    tail_text = ", ".join(b for b in tail_bits if b)
    if tail_text:
        parts.append(f"{tail_text}.")
    if doi_url:
        parts.append(doi_url)
    return " ".join(p for p in parts if p).strip()


# ---------- public enrichers ----------
def enrich_reference_via_crossref(ref: Any) -> Optional[dict[str, Any]]:
    doi = norm_doi(getattr(ref, "doi", "") or "")
    if not doi:
        return None
    csl = _fetch_csl_for_doi(doi)
    if not csl:
        return None

    title = _norm_str_or_first(csl.get("title"))
    year = _year_from_csl(csl) or ""
    journal = _norm_str_or_first(csl.get("container_title"))
    authors = [
        f"{a.get('family','')}, {a.get('given','')}".strip().rstrip(",")
        for a in _family_given_list(csl)
    ]
    apa = _apa_from_csl(csl, doi)

    updates: dict[str, Any] = {}
    if title and not getattr(ref, "title", None):
        updates["title"] = title
    if year and not getattr(ref, "issued_year", None):
        updates["issued_year"] = year
    if journal and not getattr(ref, "container_title", None):
        updates["container_title"] = journal
    if authors and not getattr(ref, "authors", None):
        updates["authors"] = authors
    if apa and not getattr(ref, "apa", None):
        updates["apa"] = apa
    if not getattr(ref, "csl", None):
        updates["csl"] = csl  # normalized CSL
    return updates or None


def enrich_capture_via_crossref(cap: Any) -> Optional[dict[str, Any]]:
    doi = norm_doi(getattr(cap, "doi", "") or (getattr(cap, "meta", {}) or {}).get("doi") or "")
    if not doi:
        return None
    csl = _fetch_csl_for_doi(doi)
    if not csl:
        return None

    title = _norm_str_or_first(csl.get("title"))
    updates: dict[str, Any] = {}
    if title and not getattr(cap, "title", None):
        updates["title"] = title

    year = _year_from_csl(csl) or ""
    if year and not getattr(cap, "year", None):
        updates["year"] = year

    journal = _norm_str_or_first(csl.get("container_title"))
    meta: dict[str, Any] = getattr(cap, "meta", {}) or {}
    if journal and not meta.get("container_title"):
        meta = {**meta, "container_title": journal}
        updates["meta"] = meta

    if not getattr(cap, "csl", None):
        updates["csl"] = csl  # normalized CSL
    return updates or None
