from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
from collections import Counter
from .utils import normalize_title


def _canon_ref_key(r: Dict[str, Any]) -> Optional[str]:
    """
    Canonicalize a reference to a stable key using DOI if present;
    otherwise a normalized title/unstructured field.
    """
    if not isinstance(r, dict):
        return None
    doi = (r.get("doi") or (r.get("csl") or {}).get("DOI") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    title = (
        r.get("title")
        or (r.get("csl") or {}).get("title")
        or r.get("unstructured")
        or ""
    )
    t = normalize_title(title)
    return f"title:{t}" if t else None


def score_docs(
    docs: List[Dict[str, Any]],
    degree: List[int],
    labels: np.ndarray,
    X: np.ndarray
) -> List[Tuple[int, float]]:
    """
    Lightweight 'importance' score across your set (not used by CLI
    for fetching external refs; kept for ranking within-set).
    """
    n = len(docs)
    if n == 0:
        return []
    deg = np.asarray(degree, dtype=float)
    if deg.size and deg.max() > 0:
        deg = deg / deg.max()

    unique, counts = np.unique(labels, return_counts=True)
    cluster_counts = {int(u): int(c) for u, c in zip(unique, counts)}
    cluster_penalty = np.array(
        [1.0 / max(1, cluster_counts.get(int(labels[i]), 1)) for i in range(n)]
    )
    # Prefer items with less obvious metadata gaps (no abstract etc.)
    has_abs = np.array([
        1.0 if ((docs[i].get("csl") or {}).get("abstract") or (docs[i].get("text") or "")) else 0.0
        for i in range(n)
    ])
    score = 0.5 * deg + 0.35 * cluster_penalty + 0.15 * (1.0 - has_abs)
    ranked = sorted([(i, float(score[i])) for i in range(n)],
                    key=lambda t: t[1], reverse=True)
    return ranked


def recommended_list(
    docs: List[Dict[str, Any]],
    degree: List[int],
    labels: np.ndarray,
    X: np.ndarray,
    k: int = 8
) -> List[Dict[str, Any]]:
    ranked = score_docs(docs, degree, labels, X)
    out = []
    for i, s in ranked[:k]:
        d = docs[i]
        out.append({
            "id": d.get("id") or d.get("citekey"),
            "title": d.get("title"),
            "doi": (d.get("meta") or {}).get("doi") or (d.get("csl") or {}).get("DOI"),
            "url": d.get("url") or (d.get("meta") or {}).get("url"),
            "score": round(float(s), 4),
        })
    return out


def recommend_next(
    docs: List[Dict[str, Any]],
    labels,
    degree: List[int],
    top_n: int = 20
) -> List[Dict[str, Any]]:
    """
    Suggest full-texts to fetch next: references cited across your set
    but not yet included in your set (by DOI or normalized title).
    """
    have = set((d.get("doi") or "").strip().lower() for d in docs if d.get("doi"))
    have_titles = set((d.get("title") or "").strip().lower() for d in docs if d.get("title"))

    counts = Counter()
    ref_map: Dict[str, Dict[str, Any]] = {}

    for d in docs:
        for r in (d.get("references") or []):
            key = _canon_ref_key(r)
            if not key:
                continue
            counts[key] += 1
            # keep the richest representation we've seen
            if key not in ref_map or len(str(r)) > len(str(ref_map[key])):
                ref_map[key] = r

    # filter out refs we already have
    cand: List[Dict[str, Any]] = []
    for key, freq in counts.most_common():
        r = ref_map[key]
        r_doi = (r.get("doi") or (r.get("csl") or {}).get("DOI") or "").strip().lower()
        r_title = (
            (r.get("title") or (r.get("csl") or {}).get("title") or "")
            .strip()
            .lower()
        )
        if (r_doi and r_doi in have) or (r_title and r_title in have_titles):
            continue
        cand.append({
            "title": r.get("title") or (r.get("csl") or {}).get("title") or r.get("unstructured"),
            "doi": r.get("doi") or (r.get("csl") or {}).get("DOI"),
            "reason": f"cited {freq}× across your notes",
            "raw": r,
        })
        if len(cand) >= top_n:
            break
    return cand
