from __future__ import annotations
from typing import Dict, Any, List, Tuple
import numpy as np
from .graph import knn_edges

def build_graph(docs: List[Dict[str, Any]], X: np.ndarray, labels, k_sim: int = 7):
    n = len(docs)
    edges = knn_edges(X, k=k_sim) if n > 1 else []
    degree = [0] * n
    for i, j, _ in edges:
        degree[i] += 1
        degree[j] += 1
    nodes = []
    for i, d in enumerate(docs):
        nodes.append({
            "id": i,
            "docId": d.get("id") or d.get("citekey"),
            "title": d.get("title"),
            "citekey": d.get("citekey"),
            "clusterId": int(labels[i]) if len(labels) > i else 0,
            "degree": degree[i],
            "doi": (d.get("meta") or {}).get("doi") or (d.get("csl") or {}).get("DOI"),
            "url": d.get("url") or (d.get("meta") or {}).get("url"),
        })
    graph = {
        "nodes": nodes,
        "edges": [{"source": i, "target": j, "weight": w} for i, j, w in edges],
    }
    return graph, degree
