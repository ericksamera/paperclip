# services/server/analysis/topics.py
from __future__ import annotations
import math, os, json, hashlib
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

from .text import tokenize, STOP

# ======================================================================================
# Utilities
# ======================================================================================

def _clean_ngram(term: str) -> bool:
    """
    True if the term should be kept. Filters any ngram that contains a stop token.
    """
    if not term: 
        return False
    parts = term.lower().split()
    if any(p in STOP for p in parts):
        return False
    # filter super-short unigrams that are mostly noise
    if len(parts) == 1 and len(parts[0]) <= 2:
        return False
    return True


def _ctfidf_top_terms_sklearn(texts: List[str], labels: List[int], k: int = 12,
                              max_features: int = 20000,
                              ngram_range: Tuple[int, int] = (1, 3)) -> Dict[int, List[str]]:
    """
    BERTopic-style c-TF-IDF approximation:
      1) Aggregate documents per cluster into a single 'class document'
      2) Vectorize those class docs -> TF-IDF across classes (use_idf=True)
      3) Take top scoring ngrams per class (filtered by STOP words)
    Returns: cluster_id -> [top terms]
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    except Exception:
        # very small fallback: unigram tf across cluster (not ideal)
        by_cluster: Dict[int, Counter[str]] = defaultdict(Counter)
        for i, c in enumerate(labels):
            by_cluster[int(c)].update(tokenize(texts[i]))
        out: Dict[int, List[str]] = {}
        for cid, tf in by_cluster.items():
            tops = [w for w, _ in tf.most_common(k*2) if _clean_ngram(w)][:k]
            out[cid] = tops
        return out

    classes = sorted(set(int(l) for l in labels))
    # aggregate docs per class
    class_docs: List[str] = []
    for cid in classes:
        buf = []
        for i, l in enumerate(labels):
            if int(l) == cid:
                buf.append(texts[i])
        class_docs.append("\n".join(buf) if buf else "")

    vec = TfidfVectorizer(stop_words="english",
                          ngram_range=ngram_range,
                          max_features=max_features,
                          min_df=1)
    X = vec.fit_transform(class_docs)  # shape (n_classes, vocab)
    terms = vec.get_feature_names_out()
    out: Dict[int, List[str]] = {}

    for row_idx, cid in enumerate(classes):
        row = X.getrow(row_idx)
        cols = row.nonzero()[1]
        scores = [(terms[j], float(row[0, j])) for j in cols]
        scores.sort(key=lambda kv: kv[1], reverse=True)
        kept: List[str] = []
        for t, _ in scores:
            if _clean_ngram(t):
                kept.append(t)
            if len(kept) >= k:
                break
        out[cid] = kept
    return out


# ======================================================================================
# Topic discovery methods
# ======================================================================================

def _fallback_topics(texts: List[str]) -> tuple[List[int], List[Dict[str, Any]], Dict[str, List[str]]]:
    n = len(texts)
    if n <= 1:
        return [0]*n, [{"cluster": 0, "top_terms": [], "size": n}], {str(i): [] for i in range(n)}
    k = min(6, max(2, int(round(math.sqrt(n)))))
    labels = [i % k for i in range(n)]
    ctf = _ctfidf_top_terms_sklearn(texts, labels, k=12)
    topics: List[Dict[str, Any]] = [{"cluster": i, "top_terms": ctf.get(i, []), "size": labels.count(i)} for i in range(k)]
    doc_terms = {str(i): tokenize(texts[i])[:10] for i in range(n)}
    return labels, topics, doc_terms


def _kmeans_topics(texts: List[str], k: int | None) -> tuple[List[int], List[Dict[str, Any]], Dict[str, List[str]]]:
    """
    TF-IDF (1–3 grams) + MiniBatchKMeans with deterministic random_state.
    Yields phrase-y top terms via c-TF-IDF and per-doc tooltips via TF-IDF row tops.
    """
    try:
        from sklearn.cluster import MiniBatchKMeans  # type: ignore
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    except Exception:
        return _fallback_topics(texts)

    min_df = 2 if len(texts) >= 8 else 1
    vec = TfidfVectorizer(stop_words="english",
                          max_features=20000,
                          ngram_range=(1, 3),
                          min_df=min_df)
    X = vec.fit_transform(texts)

    if k is None:
        k = max(2, min(12, int(round(math.sqrt(max(len(texts), 2))))))

    km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init="auto")
    labels_arr = km.fit_predict(X)
    labels = labels_arr.tolist()

    # Top-terms per cluster using c-TF-IDF (phrase-aware)
    ctf = _ctfidf_top_terms_sklearn(texts, labels, k=12)

    topics: List[Dict[str, Any]] = []
    for i in range(k):
        topics.append({"cluster": i, "top_terms": ctf.get(i, []), "size": int((labels_arr == i).sum())})

    # Doc-level top terms for tooltips (phrase-aware)
    terms = vec.get_feature_names_out()
    row = X.tocoo()
    rows: Dict[int, List[Tuple[int, float]]] = defaultdict(list)
    for r, c, v in zip(row.row, row.col, row.data):
        rows[int(r)].append((int(c), float(v)))

    doc_terms: Dict[str, List[str]] = {}
    for i in range(X.shape[0]):
        pairs = sorted(rows.get(i, []), key=lambda p: p[1], reverse=True)
        words: List[str] = []
        for c, _ in pairs:
            t = terms[c]
            if _clean_ngram(t):
                words.append(t)
            if len(words) >= 10:
                break
        doc_terms[str(i)] = words

    return labels, topics, doc_terms


def _embed_hdbscan_topics(texts: List[str]) -> tuple[List[int], List[Dict[str, Any]], Dict[str, List[str]]]:
    """
    Optional: sentence-transformers embeddings + HDBSCAN (no k to pick).
    Falls back to _fallback_topics() if libs missing.
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
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

    clusterer = hdbscan.HDBSCAN(min_cluster_size=max(2, len(texts)//20 or 2), min_samples=1, metric="euclidean")
    raw = clusterer.fit_predict(embs).tolist()

    uniq = sorted({(0 if L < 0 else L) for L in raw})
    remap = {old:i for i, old in enumerate(uniq)}
    labels = [remap.get((0 if L < 0 else L), 0) for L in raw]

    # Phrase-aware c-TF-IDF tops
    ctf = _ctfidf_top_terms_sklearn(texts, labels, k=12)
    k = len(uniq)
    topics: List[Dict[str, Any]] = [{"cluster": i, "top_terms": ctf.get(i, []), "size": labels.count(i)} for i in range(k)]
    doc_terms = {str(i): tokenize(texts[i])[:10] for i in range(len(texts))}
    return labels, topics, doc_terms


def select_topics(texts: List[str], *, prefer_embeddings: bool | None = None, k: int | None = None
                  ) -> tuple[List[int], List[Dict[str, Any]], Dict[str, List[str]], str]:
    """
    Returns (labels, topics, doc_terms, mode_used) where mode_used ∈ {"embed", "kmeans", "fallback"}.
    """
    if prefer_embeddings is None:
        prefer_embeddings = os.environ.get("PAPERCLIP_USE_EMBED", "0").lower() in {"1","true","yes"}

    if prefer_embeddings:
        labels, topics, doc_terms = _embed_hdbscan_topics(texts)
        mode = "embed"
        if len(topics) <= 1 and all(not t.get("top_terms") for t in topics):
            labels, topics, doc_terms = _kmeans_topics(texts, k)
            mode = "kmeans"
        return labels, topics, doc_terms, mode

    labels, topics, doc_terms = _kmeans_topics(texts, k)
    if len(topics) <= 1 and all(not t.get("top_terms") for t in topics):
        labels, topics, doc_terms = _fallback_topics(texts)
        return labels, topics, doc_terms, "fallback"
    return labels, topics, doc_terms, "kmeans"


# ======================================================================================
# LLM topic labeling (with persistent cache)
# ======================================================================================

def _short_label_from_terms(terms: List[str]) -> str:
    if not terms:
        return ""
    phrases = [t for t in terms if " " in t][:2]
    singles = [t for t in terms if " " not in t][:3]
    parts = phrases + singles
    if not parts:
        parts = terms[:3]
    def tc(w: str) -> str:
        return w if (len(w) <= 4 and w.isupper()) else (w.title())
    return " ".join(tc(p) for p in " · ".join(parts).split())


def _cluster_cache_key(terms: List[str], sample_texts: List[str]) -> str:
    h = hashlib.sha1()
    for t in terms[:12]:
        h.update(t.encode("utf-8")); h.update(b"|")
    for s in sample_texts[:3]:
        h.update(s[:2000].encode("utf-8", "ignore")); h.update(b"|")
    return h.hexdigest()


def _try_openai_label(cluster_docs: List[str]) -> Tuple[str, str] | None:
    """
    Returns (label, one_liner) or None on error or if API not configured.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    prompt = (
        "You label clusters of scientific papers.\n"
        "Given a sample of paragraphs from ONE cluster, return:\n"
        "1) A concise 3–7 word label; 2) One-sentence description.\n"
        "Avoid generic words (study, paper). Mention the organism/method if salient.\n\n"
        "=== Sample ===\n" + "\n\n---\n\n".join(cluster_docs[:6])
    )
    try:
        try:
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role":"system","content":"Write concise, specific topic labels."},
                          {"role":"user","content":prompt}],
                temperature=0.2,
            )
            text = (resp.choices[0].message.content or "").strip()
        except Exception:
            import openai  # type: ignore
            openai.api_key = api_key
            resp = openai.ChatCompletion.create(
                model=model,
                messages=[{"role":"system","content":"Write concise, specific topic labels."},
                          {"role":"user","content":prompt}],
                temperature=0.2,
            )
            text = resp["choices"][0]["message"]["content"].strip()
        lines = [l.strip(" -*") for l in text.splitlines() if l.strip()]
        if not lines:
            return None
        label = lines[0]
        desc = " ".join(lines[1:]) if len(lines) > 1 else ""
        return label, desc
    except Exception:
        return None


def label_topics_if_configured(
    topics: List[Dict[str, Any]],
    texts: List[str],
    labels: List[int],
    cache_dir: Path | None = None,
) -> List[Dict[str, Any]]:
    """
    Enrich topic dicts with 'label' and optional 'desc' using OpenAI when configured.
    Labels are cached in JSON at {cache_dir}/topic_label_cache.json.
    Cache key = SHA1(top_terms + snippets of sample docs).
    """
    # Build cluster -> sample docs
    cluster_docs: Dict[int, List[str]] = defaultdict(list)
    for i, c in enumerate(labels):
        if len(cluster_docs[int(c)]) < 8:  # cap to keep prompt light
            cluster_docs[int(c)].append(texts[i])

    # Load cache
    cache_path = None
    cache: Dict[str, Dict[str, str]] = {}
    if cache_dir:
        cache_path = Path(cache_dir) / "topic_label_cache.json"
        try:
            if cache_path.exists():
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    out: List[Dict[str, Any]] = []
    dirty = False

    for t in topics:
        cid = int(t.get("cluster", 0))
        terms = t.get("top_terms") or []
        default = _short_label_from_terms(terms)
        label, desc = default, ""

        # If API key present, attempt cache → LLM
        if os.environ.get("OPENAI_API_KEY"):
            sample = cluster_docs.get(cid, [])
            key = _cluster_cache_key(terms, sample)
            cached = cache.get(key)
            if cached and cached.get("label"):
                label = cached["label"]
                desc  = cached.get("desc", "")
            else:
                got = _try_openai_label(sample)
                if got:
                    label, desc = got
                    cache[key] = {"label": label, "desc": desc}
                    dirty = True

        enriched = {**t, "label": label}
        if desc:
            enriched["desc"] = desc
        out.append(enriched)

    # Persist cache if changed
    if dirty and cache_path:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    return out
