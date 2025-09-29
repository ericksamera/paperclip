# services/server/captures/xref.py
from __future__ import annotations
from typing import Dict, Any, Optional, List
from django.conf import settings
from urllib.parse import quote
import requests, json
from pathlib import Path

from paperclip.utils import norm_doi  # central DOI normalization

# NOTE: compute cache dir at access time (reads settings dynamically, easy to override in tests)
_CACHE_DIR: Path = getattr(settings, "DATA_DIR", Path(".")) / "cache" / "crossref"

def _cache_path(doi: str) -> Path:
    key = quote(norm_doi(doi), safe="")
    return _CACHE_DIR / f"{key}.json"

# ---------- in-memory cache ----------
_CACHE_MEM: dict[str, dict] = {}

def _cache_get(doi: str) -> Optional[dict]:
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
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_text(json.dumps(csl, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

# ---------- Crossref ----------
def _fetch_csl_for_doi(doi: str) -> Optional[Dict[str, Any]]:
    doi = norm_doi(doi)
    if not doi:
        return None
    # 1) cache first
    cached = _cache_get(doi)
    if cached:
        return cached
    # 2) network (short timeout; swallow any error)
    try:
        url = f"https://api.crossref.org/v1/works/{doi}/transform/application/vnd.citationstyles.csl+json"
        r = requests.get(url, timeout=5)
        if r.ok:
            csl = r.json()
            _cache_put(doi, csl)
            return csl
    except Exception:
        return None
    return None

# ---------- helpers to format CSL ----------
def _family_given_list(csl: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for a in csl.get("author", []) or []:
        fam = (a.get("family") or "").strip()
        giv = (a.get("given") or "").strip()
        if fam or giv:
            out.append({"family": fam, "given": giv})
    return out

def _year_from_csl(csl: Dict[str, Any]) -> Optional[str]:
    parts = (((csl.get("issued") or {}).get("date-parts") or []) or [])
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

def _apa_from_csl(csl: Dict[str, Any], doi: str) -> str:
    names = _family_given_list(csl)
    if names:
        if len(names) == 1:
            authors = _name_abbrev(names[0]["family"], names[0]["given"])
        elif len(names) == 2:
            a = _name_abbrev(names[0]["family"], names[0]["given"])
            b = _name_abbrev(names[1]["family"], names[1]["given"])
            authors = f"{a}, & {b}"
        else:
            a = _name_abbrev(names[0]["family"], names[0]["given"])
            authors = f"{a} et al."
    else:
        authors = ""

    year = _year_from_csl(csl) or ""
    title = (csl.get("title") or [""])[0] if isinstance(csl.get("title"), list) else (csl.get("title") or "")
    journal = (csl.get("container-title") or [""])[0] if isinstance(csl.get("container-title"), list) else (csl.get("container-title") or "")
    volume = csl.get("volume") or ""
    issue = csl.get("issue") or ""
    pages = csl.get("page") or ""
    doi_url = doi if doi.lower().startswith("http") else f"https://doi.org/{doi}"

    tail = []
    if journal: tail.append(journal)
    if volume: tail.append(volume + (f"({issue})" if issue else ""))
    if pages: tail.append(pages)
    tail_text = ", ".join([t for t in tail if t])

    parts = []
    if authors: parts.append(authors)
    if year: parts.append(f"({year}).")
    if title: parts.append(f"{title}.")
    if tail_text: parts.append(f"{tail_text}.")
    parts.append(doi_url)
    return " ".join([p for p in parts if p]).strip()

# ---------- public enrichers ----------
def enrich_reference_via_crossref(ref) -> Optional[Dict[str, Any]]:
    doi = norm_doi(getattr(ref, "doi", "") or "")
    if not doi:
        return None
    csl = _fetch_csl_for_doi(doi)
    if not csl:
        return None

    title = (csl.get("title") or [""])[0] if isinstance(csl.get("title"), list) else (csl.get("title") or "")
    year = _year_from_csl(csl) or ""
    journal = (csl.get("container-title") or [""])[0] if isinstance(csl.get("container-title"), list) else (csl.get("container-title") or "")
    authors = [f"{a.get('family','')}, {a.get('given','')}".strip().rstrip(",") for a in _family_given_list(csl)]
    apa = _apa_from_csl(csl, doi)

    updates = {}
    if title and not ref.title: updates["title"] = title
    if year and not ref.issued_year: updates["issued_year"] = year
    if journal and not ref.container_title: updates["container_title"] = journal
    if authors and not ref.authors: updates["authors"] = authors
    if apa and not ref.apa: updates["apa"] = apa
    if not ref.csl: updates["csl"] = csl
    return updates or None

def enrich_capture_via_crossref(cap) -> Optional[Dict[str, Any]]:
    doi = norm_doi(getattr(cap, "doi", "") or "")
    if not doi:
        return None
    csl = _fetch_csl_for_doi(doi)
    if not csl:
        return None

    updates = {}
    title = (csl.get("title") or [""])[0] if isinstance(csl.get("title"), list) else (csl.get("title") or "")
    if title and not cap.title: updates["title"] = title
    year = _year_from_csl(csl) or ""
    if year and not cap.year: updates["year"] = year
    journal = (csl.get("container-title") or [""])[0] if isinstance(csl.get("container-title"), list) else (csl.get("container-title") or "")
    meta = cap.meta or {}
    if journal and not meta.get("container_title"):
        meta = {**meta, "container_title": journal}
        updates["meta"] = meta
    if not cap.csl:
        updates["csl"] = csl
    return updates or None
