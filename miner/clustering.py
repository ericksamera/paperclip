import math
import numpy as np
from sklearn.cluster import KMeans

def choose_k(n: int) -> int:
    # small, robust heuristic
    return max(2, min(12, round(math.sqrt(max(2, n)))))

def kmeans_cluster(X, k: int | None = None, seed: int = 0):
    if k is None:
        k = choose_k(X.shape[0] if hasattr(X, "shape") else X.shape[0])
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    labels = km.fit_predict(X)
    centers = getattr(km, "cluster_centers_", None)
    return labels.tolist(), centers
