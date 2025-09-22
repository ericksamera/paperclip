from __future__ import annotations
from typing import Tuple, Optional
import numpy as np
from sklearn.cluster import KMeans

def _auto_k(n: int) -> int:
    if n <= 1:
        return 1
    k = max(1, int(round(np.sqrt(n))))
    return int(min(max(1, k), min(10, n)))

def kmeans_labels(X: np.ndarray, k: Optional[int] = None, random_state: int = 42) -> Tuple[np.ndarray, float]:
    n = int(X.shape[0])
    if n == 0:
        return np.array([], dtype=int), 0.0
    if k is None or k < 1 or k > n:
        k = _auto_k(n)
    if n < k:
        k = n
    if n == 1:
        return np.array([0], dtype=int), 0.0
    km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
    labels = km.fit_predict(X)
    centers = km.cluster_centers_[labels]
    dists = np.linalg.norm(X - centers, axis=1)
    compact = float(dists.mean()) if n else 0.0
    return labels.astype(int), compact
