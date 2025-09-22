from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import Normalizer


def compute_embeddings(
    docs: List[Dict[str, Any]], dim: int = 256
) -> Tuple[np.ndarray, Optional[dict]]:
    """
    Robust TF-IDF -> SVD (LSA) -> L2 normalization.
    Returns:
      X: (n, d) float32 matrix
      payload: dict with fitted vectorizer/svd/normalizer for optional reuse
    """
    texts = [(d.get("text") or "") for d in docs]

    if len(texts) == 0:
        return np.zeros((0, 0), dtype=np.float32), None

    tfidf = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        max_df=0.9,
        min_df=1,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z\-]{2,}\b",
    )
    X_tfidf = tfidf.fit_transform(texts)
    n_samples, n_features = X_tfidf.shape

    if n_samples <= 1 or n_features <= 2:
        # Degenerate small case: return normalized TF-IDF rows
        X = X_tfidf.astype(np.float32)
        norms = np.sqrt((X.multiply(X)).sum(axis=1)).A1 + 1e-8
        X = X.multiply(1.0 / norms[:, None]).toarray().astype(np.float32)
        return X, {"vectorizer": tfidf, "svd": None, "normalizer": None}

    n_components = max(2, min(dim, 256, n_samples - 1, n_features - 1))
    svd = TruncatedSVD(n_components=n_components, random_state=0)
    X_lsa = svd.fit_transform(X_tfidf)
    normalizer = Normalizer(copy=False)
    X = normalizer.fit_transform(X_lsa).astype(np.float32)

    payload = {"vectorizer": tfidf, "svd": svd, "normalizer": normalizer}
    return X, payload
