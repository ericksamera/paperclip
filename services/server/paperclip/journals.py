from __future__ import annotations

"""
Journal short-name resolver.

Behavior (unchanged from your version):
 1) Use CSL short-container-title if present
 2) Use curated overrides for common collisions (e.g., Bioinformatics)
 3) Query NLM Catalog (MedlineTA) and choose the BEST title match (not first hit)
 4) Heuristic ISO4-like fallback

Notes:
 - Network lookups can be disabled via PAPERCLIP_ENABLE_NLM=0
 - Timeouts and retmax are configurable via env vars (see constants below)
 - Safe to import when 'requests' isn't installed; network step is skipped
"""

import os
import re
from typing import Any, Dict, List, Mapping, Optional, Set, TypedDict

# --- Optional 'requests' import (keeps type-checkers happy offline) ----------
try:  # pragma: no cover - trivial import guard
    import requests  # type: ignore[no-redef]
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

# --- Config (env-tunable) ----------------------------------------------------
ENABLE_NLM_LOOKUP: bool = os.getenv("PAPERCLIP_ENABLE_NLM", "1").lower() not in {"0", "false", "no"}
NLM_ES_TIMEOUT: float = float(os.getenv("PAPERCLIP_NLM_ES_TIMEOUT", "4"))
NLM_SUMMARY_TIMEOUT: float = float(os.getenv("PAPERCLIP_NLM_SUMMARY_TIMEOUT", "6"))
NLM_RETMAX: int = int(os.getenv("PAPERCLIP_NLM_RETMAX", "10"))

# Simple in-memory cache; replace with redis/db if needed later.
_CACHE: Dict[str, str] = {}

_STOPWORDS: Set[str] = {"of", "the", "and", "in", "on", "for", "to", "a", "an"}

# Handful of high-value overrides where collisions are common.
_OVERRIDES: Dict[str, str] = {
    "bioinformatics": "Bioinformatics",
    "journal of applied microbiology": "J Appl Microbiol",
    "the journal of cell biology": "J Cell Biol",
    "journal of cell biology": "J Cell Biol",
    "nature": "Nature",
    "science": "Science",
}


# --- Types -------------------------------------------------------------------
class _NlmCandidate(TypedDict, total=False):
    title: str
    medlineta: str


# --- Helpers -----------------------------------------------------------------
def _from_csl(csl: Mapping[str, Any] | None) -> Optional[str]:
    if not isinstance(csl, Mapping):
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


def _tokset(s: str) -> Set[str]:
    # letters only + filter stopwords (stable for matching)
    toks = [w for w in re.findall(r"[A-Za-z]+", s.lower()) if w not in _STOPWORDS]
    return set(toks)


def _jaccard(a: Set[str], b: Set[str]) -> float:
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


def _pick_best_medlineta(target_title: str, candidates: List[_NlmCandidate]) -> Optional[str]:
    """
    Choose the medlineta whose record title is closest to the requested title.
    candidates: [{'title': str, 'medlineta': str}, ...]
    """
    ttoks = _tokset(target_title)
    best: Optional[str] = None
    # (sim desc, medlineta len asc, title len asc)
    best_key: tuple[float, int, int] = (-1.0, 10**9, 10**9)
    for rec in candidates:
        mt = (rec.get("medlineta") or "").strip()
        rtitle = (rec.get("title") or "").strip()
        if not mt or not rtitle:
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


# --- Public API ---------------------------------------------------------------
def get_short_journal_name(title: str | None, csl: Mapping[str, Any] | None = None) -> str:
    """
    Best-effort short name (cached). See module docstring for strategy.
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
    cached = _CACHE.get(t)
    if cached:
        return cached

    # 3) NLM E-utilities (best-effort)
    picked: Optional[str] = None
    if ENABLE_NLM_LOOKUP and requests is not None:  # type: ignore[truthy-bool]
        candidates: List[_NlmCandidate] = []
        try:
            # esearch: constrain to full journal title and journals subset
            es_params: Dict[str, str] = {
                "db": "nlmcatalog",
                "retmode": "json",
                "retmax": str(NLM_RETMAX),
                "term": f'"{t}"[Title] AND journalspub[subset]',
            }
            es = requests.get(  # type: ignore[call-arg]
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params=es_params,
                timeout=NLM_ES_TIMEOUT,
            )
            if es.ok:
                ids = (es.json().get("esearchresult", {}) or {}).get("idlist", [])  # type: ignore[assignment]
                if ids:
                    su = requests.get(  # type: ignore[call-arg]
                        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                        params={"db": "nlmcatalog", "retmode": "json", "id": ",".join(ids)},
                        timeout=NLM_SUMMARY_TIMEOUT,
                    )
                    if su.ok:
                        data = su.json().get("result", {}) or {}
                        for sid in ids:
                            rec = data.get(sid) or {}
                            candidates.append(
                                _NlmCandidate(
                                    title=rec.get("title") or rec.get("fulljournalname") or "",
                                    medlineta=rec.get("medlineta") or "",
                                )
                            )
        except Exception:
            candidates = []

        if candidates:
            picked = _pick_best_medlineta(t, candidates)

    if picked:
        _CACHE[t] = picked
        return picked

    # 4) Last-resort heuristic
    short = _heuristic_iso4(t)
    _CACHE[t] = short
    return short


__all__ = ["get_short_journal_name"]
