from __future__ import annotations
import numpy as np
from typing import List, Tuple
from .text import text_for_embedding

class Embedder:
    """
    Tries sentence-transformers; falls back to TF-IDF if not available.
    """
    def __init__(self, model: str | None = None):
        self.backend = "tfidf"
        self.model_name = model or "sentence-transformers/all-MiniLM-L6-v2"
        self._model = None
        self._tfidf = None
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            self._model = SentenceTransformer(self.model_name)
            self.backend = "sbert"
        except Exception:
            self._model = None

    def fit_transform(self, docs: List[dict]) -> Tuple[np.ndarray, List[str]]:
        texts = [text_for_embedding(d) for d in docs]
        if self._model is not None:
            X = np.asarray(self._model.encode(texts, normalize_embeddings=True))
            return X, texts
        # TF-IDF fallback
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
        self._tfidf = TfidfVectorizer(max_features=2048, ngram_range=(1,2))
        Xs = self._tfidf.fit_transform(texts)
        # L2 normalize to approximate cosine
        X = Xs.astype("float32")
        norms = np.sqrt((X.multiply(X)).sum(axis=1)).A1 + 1e-8
        X = X.multiply(1.0 / norms[:, None])
        return X.toarray(), texts
