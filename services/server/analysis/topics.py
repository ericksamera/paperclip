# services/server/analysis/topics.py
from __future__ import annotations
import math, os
from collections import Counter
from typing import Any, Dict, List, Tuple

from .text import tokenize, STOP

def _fallback_topics(texts: List[str]) -> tuple[List[int], List[Dict[str, Any]], Dict[str, List[str]]]:
    n = len(texts)
    if n <= 1:
        return [0]*n, [{"cluster": 0, "top_terms": [], "size": n}], {str(i): [] for i in range(n)}
    k = min(6, max(2, int(round(math.sqrt(n)))))
    labels = [i % k for i in range(n)]

    topics: List[Dict[str, Any]] = []
    for i in range(k):
        bag: Counter[str] = Counter()
        for idx, lab in enumerate(labels):
            if lab == i:
                bag.update(tokenize(texts[idx]))
        topics.append({"cluster": i, "top_terms": [w for w, _ in bag.most_common(12)], "size": labels.count(i)})

    doc_terms = {str(i): tokenize(texts[i])[:10] for i in range(n)}
    return labels, topics, doc_terms

def _kmeans_topics(texts: List[str], k: int | None) -> tuple[List[int], List[Dict[str, Any]], Dict[str, List[str]]]:
    try:
        from sklearn.cluster import MiniBatchKMeans
        from sklearn.feature_extraction.text import TfidfVectorizer
    except Exception:
        return _fallback_topics(texts)

    min_df = 2 if len(texts) >= 8 else 1
    vec = TfidfVectorizer(stop_words="english", max_features=8000, ngram_range=(1, 2), min_df=min_df)
    X = vec.fit_transform(texts)

    if k is None:
        k = max(2, min(12, int(round(math.sqrt(max(len(texts), 2))))))

    km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init="auto")
    labels = km.fit_predict(X)

    terms = vec.get_feature_names_out()
    centers = km.cluster_centers_

    topics: List[Dict[str, Any]] = []
    for i in range(k):
        order = centers[i].argsort()[::-1]
        top: List[str] = []
        for j in order:
            t = terms[j]
            if t in STOP: continue
            if " " in t:
                a, b = t.split(" ", 1)
                if a in STOP or b in STOP:
                    continue
            top.append(t)
            if len(top) >= 12:
                break
        topics.append({"cluster": i, "top_terms": top, "size": int((labels == i).sum())})

    # doc top terms
    doc_terms: Dict[str, List[str]] = {}
    for idx in range(X.shape[0]):
        row = X.getrow(idx).tocoo()
        pairs = sorted(zip(row.col, row.data), key=lambda p: p[1], reverse=True)
        words: List[str] = []
        for c, _ in pairs:
            t = terms[c]
            if t in STOP: continue
            if " " in t:
                a, b = t.split(" ", 1)
                if a in STOP or b in STOP:
                    continue
            words.append(t)
            if len(words) >= 10: break
        doc_terms[str(idx)] = words

    return labels.tolist(), topics, doc_terms

def _embed_hdbscan_topics(texts: List[str]) -> tuple[List[int], List[Dict[str, Any]], Dict[str, List[str]]]:
    """
    Optional: sentence-transformers embeddings + HDBSCAN (no k to pick).
    Falls back to _fallback_topics() if libs missing.
    """
    try:
        from sentence_transformers import SentenceTransformer
        import hdbscan  # type: ignore
    except Exception:
        return _fallback_topics(texts)

    model_name = os.environ.get("PAPERCLIP_EMBED_MODEL", "allenai/specter2_base")
    try:
        model = SentenceTransformer(model_name)
    except Exception:
        return _fallback_topics(texts)

    embs = model.encode(texts, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
    if len(texts) <= 2:
        return [0]*len(texts), [{"cluster":0,"top_terms":[],"size":len(texts)}], {str(i): tokenize(t)[:10] for i, t in enumerate(texts)}

    # HDBSCAN: cluster; -1 = noise → own tiny bucket 0
    clusterer = hdbscan.HDBSCAN(min_cluster_size=max(2, len(texts)//20 or 2), min_samples=1, metric="euclidean")
    labels = clusterer.fit_predict(embs).tolist()

    # map negative to 0, compress ids to 0..K-1
    uniq = sorted({(0 if L < 0 else L) for L in labels})
    remap = {old:i for i, old in enumerate(uniq)}
    mlabels = [remap.get((0 if L < 0 else L), 0) for L in labels]
    k = len(uniq)

    topics: List[Dict[str, Any]] = []
    for i in range(k):
        bag: Counter[str] = Counter()
        for idx, lab in enumerate(mlabels):
            if lab == i:
                bag.update(tokenize(texts[idx]))
        topics.append({"cluster": i, "top_terms": [w for w, _ in bag.most_common(12)], "size": mlabels.count(i)})

    doc_terms = {str(i): tokenize(texts[i])[:10] for i in range(len(texts))}
    return mlabels, topics, doc_terms

def select_topics(texts: List[str], *, prefer_embeddings: bool | None = None, k: int | None = None
                  ) -> tuple[List[int], List[Dict[str, Any]], Dict[str, List[str]], str]:
    """
    Returns (labels, topics, doc_terms, mode_used)
    mode_used ∈ {"embed", "kmeans", "fallback"}
    """
    if prefer_embeddings is None:
        prefer_embeddings = os.environ.get("PAPERCLIP_USE_EMBED", "0").lower() in {"1","true","yes"}

    if prefer_embeddings:
        labels, topics, doc_terms = _embed_hdbscan_topics(texts)
        mode = "embed"
        # If embed path just returned trivial fallback (1 cluster, 0 size terms), try kmeans
        if len(topics) <= 1 and all(not t.get("top_terms") for t in topics):
            labels, topics, doc_terms = _kmeans_topics(texts, k)
            mode = "kmeans"
        return labels, topics, doc_terms, mode

    # Prefer KMeans, then fallback
    labels, topics, doc_terms = _kmeans_topics(texts, k)
    if len(topics) <= 1 and all(not t.get("top_terms") for t in topics):
        labels, topics, doc_terms = _fallback_topics(texts)
        return labels, topics, doc_terms, "fallback"
    return labels, topics, doc_terms, "kmeans"
