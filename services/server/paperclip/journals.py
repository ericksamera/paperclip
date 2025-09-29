# services/server/paperclip/journals.py
from __future__ import annotations
import re
from typing import Optional, Tuple, List, Dict
import requests

# Simple in-memory cache; replace with redis/db if needed later.
_CACHE: dict[str, str] = {}

_STOPWORDS = {"of", "the", "and", "in", "on", "for", "to", "a", "an"}

# Handful of high-value overrides where collisions are common.
_OVERRIDES = {
    "bioinformatics": "Bioinformatics",
    "journal of applied microbiology": "J Appl Microbiol",
    "the journal of cell biology": "J Cell Biol",
    "journal of cell biology": "J Cell Biol",
    "nature": "Nature",
    "science": "Science",
}

def _from_csl(csl: dict | None) -> Optional[str]:
    if not isinstance(csl, dict):
        return None
    for k in ("short-container-title", "container-title-short", "container_title_short"):
        v = csl.get(k)
        if isinstance(v, list) and v:
            return str(v[0]).strip()
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())

def _tokset(s: str) -> set[str]:
    toks = [w for w in re.findall(r"[A-Za-z]+", s.lower()) if w not in _STOPWORDS]
    return set(toks)

def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b) or 1
    return inter / union

def _heuristic_iso4(title: str) -> str:
    # crude ISO4-ish fallback: take initials of content words
    parts = [w for w in re.findall(r"[A-Za-z]+", title) if w.lower() not in _STOPWORDS]
    if not parts:
        return title
    abbr = "".join(p[0].upper() for p in parts)
    return abbr if len(abbr) >= 3 else title

def _pick_best_medlineta(target_title: str, candidates: List[Dict]) -> Optional[str]:
    """
    Choose the medlineta whose record title is closest to the requested title.
    candidates: [{'title': str, 'medlineta': str}, ...]
    """
    ttoks = _tokset(target_title)
    best = None
    best_key: Tuple[float, int, int] = (-1.0, 10**9, 10**9)  # (sim desc, medlineta len asc, title len asc)

    for rec in candidates:
        rtitle = (rec.get("title") or "").strip()
        mt = (rec.get("medlineta") or "").strip()
        if not rtitle or not mt:
            continue

        # Exact-normalized match wins immediately
        if _norm(rtitle) == _norm(target_title):
            return mt

        sim = _jaccard(ttoks, _tokset(rtitle))
        key = (sim, len(mt), len(rtitle))
        if key > best_key:
            best_key = key
            best = mt

    return best

def get_short_journal_name(title: str | None, csl: dict | None = None) -> str:
    """
    Best-effort short name:
      1) Use CSL short-container-title if present
      2) Use curated overrides for common collisions (e.g., Bioinformatics)
      3) Query NLM Catalog (MedlineTA) and choose the BEST title match (not first hit)
      4) Heuristic ISO4-like fallback
    Cached per process.
    """
    if not title:
        return ""
    t = title.strip()
    if not t:
        return ""

    # 1) CSL first
    short = _from_csl(csl)
    if short:
        return short

    # 2) Curated overrides
    ov = _OVERRIDES.get(t.lower())
    if ov:
        return ov

    # 2b) If single concise word (e.g., "Bioinformatics"), just keep it.
    #     This avoids mapping a simple title to an unrelated "Transactions" journal.
    if " " not in t and len(t) <= 20:
        return t

    # 3) Cache
    if t in _CACHE:
        return _CACHE[t]

    # 3) NLM E-utilities (best-effort)
    candidates: List[Dict] = []
    try:
        # Constrain to full journal title and journals subset
        es = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "nlmcatalog", "retmode": "json", "retmax": 10,
                    "term": f"\"{t}\"[Title] AND journalspub[subset]"},
            timeout=4,
        )
        if es.ok:
            ids = (es.json().get("esearchresult", {}) or {}).get("idlist", [])
            if ids:
                su = requests.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                    params={"db": "nlmcatalog", "retmode": "json", "id": ",".join(ids)},
                    timeout=6,
                )
                if su.ok:
                    data = su.json().get("result", {}) or {}
                    for sid in ids:
                        rec = data.get(sid) or {}
                        candidates.append({
                            "title": rec.get("title") or rec.get("fulljournalname"),
                            "medlineta": rec.get("medlineta"),
                        })
    except Exception:
        candidates = []

    picked = _pick_best_medlineta(t, candidates) if candidates else None
    if picked:
        _CACHE[t] = picked
        return picked

    # 4) Last-resort heuristic
    short = _heuristic_iso4(t)
    _CACHE[t] = short
    return short
