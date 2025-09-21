from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, List
import requests, json, re
from urllib.parse import quote
from django.conf import settings

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")

# ---------- Normalization helpers ----------

def normalize_doi(s: str) -> Optional[str]:
    if not s: return None
    s = s.strip()
    s = re.sub(r"(?i)^(https?://(dx\.)?doi\.org/)", "", s)
    s = re.sub(r"(?i)^doi:\s*", "", s)
    m = DOI_RE.search(s)
    return m.group(0).lower() if m else None

def first_str(x):
    if isinstance(x, list):
        return x[0] if x else None
    return x

def message_to_csl(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Crossref 'message' to CSL-ish JSON for the main work."""
    if not isinstance(msg, dict): msg = {}
    authors = []
    for a in msg.get("author") or []:
        fam = (a.get("family") or "").strip()
        giv = (a.get("given") or "").strip()
        if fam or giv:
            authors.append({"family": fam, "given": giv})
    issued = (msg.get("issued") or msg.get("published-print") or msg.get("published-online") or {})
    csl = {
        "type": msg.get("type") or "article-journal",
        "title": first_str(msg.get("title")),
        "container-title": first_str(msg.get("container-title")),
        "author": authors,
        "issued": issued if isinstance(issued, dict) else {},
        "volume": msg.get("volume"),
        "issue": msg.get("issue"),
        "page": msg.get("page"),
        "publisher": msg.get("publisher"),
        "URL": msg.get("URL"),
        "DOI": msg.get("DOI"),
        "ISSN": msg.get("ISSN"),
    }
    return {k: v for k, v in csl.items() if v not in (None, "", [])}

def csl_to_doc_meta(csl: Dict[str, Any]) -> Dict[str, Any]:
    """Map CSL for the main work into capture.meta fields."""
    meta: Dict[str, Any] = {}
    if not isinstance(csl, dict): return meta
    meta["title"] = csl.get("title")
    meta["journal"] = first_str(csl.get("container-title")) or csl.get("container_title")
    # Issued year
    y = None
    issued = csl.get("issued") or {}
    dp = issued.get("date-parts") or issued.get("date_parts") or []
    if isinstance(dp, list) and dp and isinstance(dp[0], (list, tuple)) and dp[0]:
        y = str(dp[0][0])
    meta["issued_year"] = y
    meta["volume"] = csl.get("volume")
    meta["issue"] = csl.get("issue")
    meta["pages"] = csl.get("page") or csl.get("pages")
    meta["publisher"] = csl.get("publisher")
    issn = csl.get("ISSN")
    if isinstance(issn, list) and issn: issn = issn[0]
    meta["issn"] = issn
    meta["url"] = csl.get("URL") or (("https://doi.org/" + csl["DOI"]) if csl.get("DOI") else None)
    meta["authors"] = csl.get("author") or []
    if csl.get("DOI"): meta["doi"] = csl["DOI"]
    return {k: v for k, v in meta.items() if v not in (None, "", [])}

# ---------- External APIs ----------

def fetch_crossref(doi: str, timeout: float = 10.0) -> Tuple[Optional[Dict[str, Any]], Optional[requests.Response]]:
    doi_norm = normalize_doi(doi)
    if not doi_norm: return None, None
    url = f"https://api.crossref.org/works/{quote(doi_norm)}"
    params = {}
    mail = getattr(settings, "CROSSREF_MAILTO", None)
    if mail: params["mailto"] = mail
    hdrs = {"User-Agent": f"paperclip/0.1 (+mailto:{mail})" if mail else "paperclip/0.1"}
    try:
        r = requests.get(url, params=params, headers=hdrs, timeout=timeout)
        if r.status_code == 200:
            j = r.json()
            return j.get("message"), r
        return None, r
    except requests.RequestException:
        return None, None

def fetch_openalex(doi: str, timeout: float = 10.0) -> Tuple[Optional[Dict[str, Any]], Optional[requests.Response]]:
    doi_norm = normalize_doi(doi)
    if not doi_norm: return None, None
    url = f"https://api.openalex.org/works/doi:{doi_norm}"
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json(), r
        return None, r
    except requests.RequestException:
        return None, None

def openalex_to_csl(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal mapping from OpenAlex single-work to CSL-ish JSON."""
    if not isinstance(obj, dict): obj = {}
    # Authors: best-effort split of display_name into given/family
    authors = []
    for au in obj.get("authorships") or []:
        name = ((au.get("author") or {}).get("display_name") or "").strip()
        if not name: continue
        if "," in name:
            fam, giv = [p.strip() for p in name.split(",", 1)]
        else:
            parts = name.split()
            fam = parts[-1] if parts else ""
            giv = " ".join(parts[:-1]) if len(parts) > 1 else ""
        authors.append({"family": fam, "given": giv})
    host = obj.get("host_venue") or {}
    biblio = obj.get("biblio") or {}
    csl = {
        "type": "article-journal",
        "title": obj.get("title"),
        "container-title": host.get("display_name"),
        "author": authors,
        "issued": {"date-parts": [[obj.get("publication_year")]]} if obj.get("publication_year") else {},
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "page": _join_pages(biblio.get("first_page"), biblio.get("last_page")),
        "publisher": host.get("publisher"),
        "URL": obj.get("primary_location", {}).get("landing_page_url") or obj.get("ids", {}).get("openalex"),
        "DOI": normalize_doi(obj.get("doi") or obj.get("ids", {}).get("doi") or ""),
        "ISSN": [host.get("issn_l")] if host.get("issn_l") else None,
    }
    return {k: v for k, v in csl.items() if v not in (None, "", [], {})}

def _join_pages(fp: Any, lp: Any) -> Optional[str]:
    if not fp and not lp: return None
    if fp and lp: return f"{fp}-{lp}"
    return fp or lp

def enrich_from_doi(doi: str) -> Optional[Dict[str, Any]]:
    """
    Returns: {
      "source": "crossref"|"openalex",
      "csl": {...},         # CSL-like JSON for the main work
      "raw": {...}          # raw API payload for transparency
    } or None
    """
    msg, r = fetch_crossref(doi)
    if msg:
        csl = message_to_csl(msg)
        return {"source": "crossref", "csl": csl, "raw": msg}
    # Fallback to OpenAlex
    obj, r2 = fetch_openalex(doi)
    if obj:
        csl = openalex_to_csl(obj)
        return {"source": "openalex", "csl": csl, "raw": obj}
    return None
