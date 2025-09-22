from __future__ import annotations
import numpy as np
from typing import Any, Dict, List

def compute_badges(docs: List[Dict[str, Any]], degree: List[int],
                   cluster_sizes: Dict[int, int], labels) -> Dict[str, List[str]]:
    deg = np.array(degree)
    hi = np.percentile(deg, 75) if len(deg) else 0
    badges: Dict[str, List[str]] = {}
    for i, d in enumerate(docs):
        b: List[str] = []
        if d.get("oa") or d.get("pdf_url") or d.get("open_url"):
            b.append("OA")
        if degree[i] >= hi:
            b.append("Highly connected")
        c = int(labels[i]) if len(labels) > i else 0
        if cluster_sizes.get(c, 0) <= max(2, int(0.1 * max(1, len(docs)))):
            b.append("Under‑covered theme")
        if not (d.get("csl") or {}).get("DOI") and not (d.get("csl") or {}).get("doi"):
            b.append("Needs metadata")
        badges[d.get("citekey") or str(i)] = b
    return badges
