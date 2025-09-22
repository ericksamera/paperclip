from __future__ import annotations
from typing import Dict, Any, List, Sequence, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


def label_clusters(
    docs: List[Dict[str, Any]],
    labels: Sequence[int],
    top_k: int = 6
) -> Tuple[Dict[int, Dict[str, Any]], List[str]]:
    """
    Build short labels for clusters from TF-IDF top terms.
    Accepts docs + labels (no external payload required).
    """
    n = len(docs)
    if n == 0:
        return {}, []

    labels = np.asarray(labels, dtype=int)
    texts = [(d.get("text") or "") for d in docs]

    vec = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        max_features=20000,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z\-]{2,}\b",
    )
    # If all texts are empty, avoid ValueError from vectorizer
    if not any(t.strip() for t in texts):
        per_doc = ["misc"] * n
        return {}, per_doc

    X = vec.fit_transform(texts)
    vocab = np.asarray(vec.get_feature_names_out())

    clusters: Dict[int, Dict[str, Any]] = {}

    for c in np.unique(labels):
        idx = np.where(labels == c)[0]
        if idx.size == 0:
            continue
        # centroid over sparse rows; mean() yields 1 x F matrix
        centroid = X[idx].mean(axis=0)
        arr = np.asarray(centroid).ravel()
        top_idx = arr.argsort()[-top_k:][::-1]
        terms = vocab[top_idx].tolist()
        title = ", ".join(terms[:3])
        clusters[int(c)] = {
            "label": title,
            "top_terms": terms,
            "size": int(idx.size),
            "example_titles": [docs[i].get("title") for i in idx[:3]],
        }

    per_doc = [
        clusters[int(labels[i])]["label"] if int(labels[i]) in clusters else "misc"
        for i in range(n)
    ]
    return clusters, per_doc
