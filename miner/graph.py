from __future__ import annotations
from typing import List, Tuple
import numpy as np

def cosine_sim_matrix(X: np.ndarray) -> np.ndarray:
    if X.size == 0:
        return np.zeros((0, 0), dtype=np.float32)
    norms = np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    Y = X / norms
    return (Y @ Y.T).astype(np.float32)

def knn_edges(X: np.ndarray, k: int = 7) -> List[Tuple[int, int, float]]:
    n = int(X.shape[0])
    if n <= 1:
        return []
    k = int(max(1, min(k, n - 1)))
    sims = cosine_sim_matrix(X)
    edges = []
    for i in range(n):
        row = sims[i].copy()
        row[i] = -1.0
        idx = np.argpartition(row, -k)[-k:]
        idx = idx[np.argsort(row[idx])[::-1]]
        for j in idx:
            if i < j:
                edges.append((i, int(j), float(row[int(j)])))
    return edges
