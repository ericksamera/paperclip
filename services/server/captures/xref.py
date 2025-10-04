# services/server/captures/xref.py
from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from django.conf import settings

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


# ---------- Crossref ----------
def _fetch_csl_for_doi(doi: str) -> dict[str, Any] | None:
    doi = norm_doi(doi)
    if not doi:
        return None
    cached = _cache_get(doi)
    if cached:
        return cached
    try:
        url = f"https://api.crossref.org/v1/works/{doi}/transform/application/vnd.citationstyles.csl+json"
        r = requests.get(
            url,
            timeout=ENRICH_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.citationstyles.csl+json"},
        )
        if r.ok:
            csl = r.json()
            _cache_put(doi, csl)
            return csl
    except Exception:
        return None
    return None


# ---------- helpers to format CSL ----------
def _family_given_list(csl: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for a in csl.get("author", []) or []:
        fam = (a.get("family") or "").strip()
        giv = (a.get("given") or "").strip()
        if fam or giv:
            out.append({"family": fam, "given": giv})
    return out


def _year_from_csl(csl: dict[str, Any]) -> str | None:
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


def _apa_from_csl(csl: dict[str, Any], doi: str) -> str:
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
    raw_title = csl.get("title")
    title = (raw_title or [""])[0] if isinstance(raw_title, list) else (raw_title or "")
    raw_ct = csl.get("container-title")
    journal = (raw_ct or [""])[0] if isinstance(raw_ct, list) else (raw_ct or "")
    volume = str(csl.get("volume") or "")
    issue = str(csl.get("issue") or "")
    pages = str(csl.get("page") or "")
    doi_url = f"https://doi.org/{quote(doi)}" if doi else ""
    parts: list[str] = []
    if authors:
        parts.append(f"{authors}.")
    if year:
        parts.append(f"({year}).")
    if title:
        parts.append(f"{title}.")
    if journal:
        parts.append(journal)
    tail_bits: list[str] = []
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
def enrich_reference_via_crossref(ref: Any) -> dict[str, Any] | None:
    doi = norm_doi(getattr(ref, "doi", "") or "")
    if not doi:
        return None
    csl = _fetch_csl_for_doi(doi)
    if not csl:
        return None
    raw_title = csl.get("title")
    title = (raw_title or [""])[0] if isinstance(raw_title, list) else (raw_title or "")
    year = _year_from_csl(csl) or ""
    raw_ct = csl.get("container-title")
    journal = (raw_ct or [""])[0] if isinstance(raw_ct, list) else (raw_ct or "")
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
        updates["csl"] = csl
    return updates or None


def enrich_capture_via_crossref(cap: Any) -> dict[str, Any] | None:
    doi = norm_doi(getattr(cap, "doi", "") or (getattr(cap, "meta", {}) or {}).get("doi") or "")
    if not doi:
        return None
    csl = _fetch_csl_for_doi(doi)
    if not csl:
        return None
    raw_title = csl.get("title")
    title = (raw_title or [""])[0] if isinstance(raw_title, list) else (raw_title or "")
    updates: dict[str, Any] = {}
    if title and not getattr(cap, "title", None):
        updates["title"] = title
    year = _year_from_csl(csl) or ""
    if year and not getattr(cap, "year", None):
        updates["year"] = year
    raw_ct = csl.get("container-title")
    journal = (raw_ct or [""])[0] if isinstance(raw_ct, list) else (raw_ct or "")
    meta: dict[str, Any] = getattr(cap, "meta", {}) or {}
    if journal and not meta.get("container_title"):
        meta = {**meta, "container_title": journal}
        updates["meta"] = meta
    if not getattr(cap, "csl", None):
        updates["csl"] = csl
    return updates or None
