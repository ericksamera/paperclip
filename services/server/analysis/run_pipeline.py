# services/server/analysis/run_pipeline.py
from __future__ import annotations
import hashlib
import json
import math
import os
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Tuple
from collections import Counter, defaultdict

import numpy as np

from .graph_build import collect_docs, build_citation_edges, compute_metrics
from .topics import select_topics, label_topics_if_configured
from .text import tokenize
from paperclip.utils import norm_doi


# ----------------------------- helpers -----------------------------

def _stable_ref_id(doi: str, title: str, year: str) -> str:
    key = (doi or "").strip().lower() or (title.strip().lower() + "|" + year.strip())
    key = key or title or "ref"
    return "x_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _mutual_edges(directed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pair = defaultdict(lambda: [0, 0])  # (a<b ? [a->b, b->a] : [b->a, a->b])
    for e in directed:
        a, b, w = e["source"], e["target"], int(e.get("weight", 1))
        if a == b:
            continue
        u, v = (a, b) if a < b else (b, a)
        if a < b:
            pair[(u, v)][0] += w
        else:
            pair[(u, v)][1] += w
    out: List[Dict[str, Any]] = []
    for (u, v), (ab, ba) in pair.items():
        if ab and ba:
            out.append({"source": u, "target": v, "weight": ab + ba})
    return out


def _biblio_coupling(docs) -> List[Dict[str, Any]]:
    refs = {d.id: set(d.refs_doi) for d in docs}
    ids = [d.id for d in docs]
    out: List[Dict[str, Any]] = []
    for a, b in combinations(ids, 2):
        inter = refs[a] & refs[b]
        if inter:
            out.append({"source": a, "target": b, "weight": len(inter)})
    return out


def _co_citation(directed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_src: Dict[str, set[str]] = defaultdict(set)
    for e in directed:
        by_src[e["source"]].add(e["target"])
    w = defaultdict(int)
    for _s, targets in by_src.items():
        for a, b in combinations(sorted(targets), 2):
            w[(a, b)] += 1
    return [{"source": a, "target": b, "weight": c} for (a, b), c in w.items() if c > 0]


# ----------------------------- embeddings + semantic edges -----------------------------

def _safe_normalize_rows(M: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return M / norms


def _embed_texts(texts: List[str]) -> Tuple[np.ndarray, str]:
    model_name = os.environ.get("PAPERCLIP_EMBED_MODEL", "allenai/specter2_base")
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        model = SentenceTransformer(model_name)
        embs = model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(embs, dtype="float32"), model_name
    except Exception:
        pass

    # Fallback: TF-IDF + TruncatedSVD (dense 128-dim)
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
        from sklearn.decomposition import TruncatedSVD  # type: ignore
        vec = TfidfVectorizer(stop_words="english", max_features=20000, ngram_range=(1, 2), min_df=1)
        X = vec.fit_transform(texts)
        k = min(128, max(16, min(X.shape[0]-1, X.shape[1]-1)))
        svd = TruncatedSVD(n_components=k, random_state=42)
        Z = svd.fit_transform(X)
        Z = _safe_normalize_rows(np.asarray(Z, dtype="float32"))
        return Z, "tfidf-svd"
    except Exception:
        # Final fallback: bag-of-words count of tokens
        toks = [tokenize(t) for t in texts]
        vocab = {}
        rows = []
        for ts in toks:
            row = {}
            for w in ts:
                idx = vocab.setdefault(w, len(vocab))
                row[idx] = row.get(idx, 0.0) + 1.0
            rows.append(row)
        n, d = len(texts), len(vocab)
        M = np.zeros((n, max(1, d)), dtype="float32")
        for i, row in enumerate(rows):
            for j, val in row.items():
                M[i, j] = val
        M = _safe_normalize_rows(M)
        return M, "bow"


def _knn_edges(emb: np.ndarray, ids: List[str], *, k: int = 8, thresh: float = 0.32) -> List[Dict[str, Any]]:
    if emb.shape[0] <= 2:
        return []
    X = _safe_normalize_rows(emb.astype("float32"))
    sims = X @ X.T
    np.fill_diagonal(sims, -1.0)

    k = max(1, min(k, sims.shape[0] - 1))
    seen: set[Tuple[int, int]] = set()
    edges: List[Dict[str, Any]] = []

    for i in range(sims.shape[0]):
        row = sims[i]
        idx = np.argpartition(row, -k)[-k:]
        idx = idx[np.argsort(row[idx])[::-1]]
        for j in idx:
            a, b = (i, int(j)) if i < j else (int(j), i)
            if (a, b) in seen:
                continue
            sim = float(row[j])
            if sim < thresh:
                continue
            seen.add((a, b))
            w = max(1, int(round(sim * 100)))
            edges.append({"source": ids[a], "target": ids[b], "weight": w})
    return edges


# ----------------------------- main pipeline -----------------------------

def run(out_dir: Path, k: int | None = None) -> Dict[str, Any]:
    """
    Builds nodes/edges and writes graph.json into out_dir.
    Adds: semantic edges, topic nodes, topic relations, gap flags, and LLM topic labels (cached).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1) Captures → documents
    docs = collect_docs()
    if not docs:
        data = {"nodes": [], "edges": [], "edgesets": {}, "topics": [], "k": 0, "mode": "empty"}
        (out_dir / "graph.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"stats": {"docs": 0, "edges": 0}, "k": 0, "mode": "empty"}

    # --- 2) Directed capture→capture edges (by DOI)
    doc_edges = build_citation_edges(docs)

    # --- 3) Topics on capture texts
    texts = [d.text for d in docs]
    labels, topics, doc_terms_map, mode = select_topics(texts, k=k)
    # LLM labels with persistent cache at data/analysis/topic_label_cache.json
    topics = label_topics_if_configured(topics, texts, labels, cache_dir=out_dir.parent)

    # --- 4) External reference nodes + edges (uncaptured citations)
    doi_to_doc = {d.doi: d for d in docs if d.doi}
    ext_nodes: Dict[str, Dict[str, Any]] = {}
    ext_votes: Dict[str, Counter] = defaultdict(Counter)
    ext_edges: List[Dict[str, Any]] = []

    for i, d in enumerate(docs):
        c = int(labels[i]) if labels else 0
        for r in d.refs:
            rdoi = norm_doi(r.get("doi"))
            if rdoi and rdoi in doi_to_doc:
                continue
            title = (r.get("title") or "").strip()
            year = str(r.get("issued_year") or "")
            if not (rdoi or title):
                continue
            rid = _stable_ref_id(rdoi, title, year)
            if rid not in ext_nodes:
                ext_nodes[rid] = {
                    "id": rid,
                    "title": title or (rdoi or "(reference)"),
                    "year": year,
                    "doi": rdoi,
                    "url": "",
                    "external": True,
                    "terms": tokenize(title)[:8] if title else [],
                }
            ext_votes[rid][c] += 1
            ext_edges.append({"source": d.id, "target": rid, "weight": 1})

    # --- 5) Nodes (captures first)
    nodes: List[Dict[str, Any]] = []
    id_order: List[str] = []

    cluster_counts: Dict[int, int] = Counter(int(c) for c in labels) if labels else Counter({0: len(docs)})

    for i, d in enumerate(docs):
        n = {
            "id": d.id,
            "title": d.title,
            "year": d.year,
            "doi": d.doi,
            "url": d.url,
            "has_doi": bool(d.doi),
            "external": False,
            "cluster": int(labels[i]) if labels else 0,
            "degree": 0, "pagerank": None,
            "terms": doc_terms_map.get(str(i), []) or tokenize(d.text)[:8],
        }
        nodes.append(n)
        id_order.append(d.id)

    # --- 6) Topic nodes + membership edges
    topic_nodes: List[Dict[str, Any]] = []
    edges_topic_membership: List[Dict[str, Any]] = []
    for t in topics:
        cid = int(t.get("cluster", 0))
        label = t.get("label") or " · ".join((t.get("top_terms") or [])[:3]) or f"Topic {cid}"
        tid = f"T{cid}"
        tn = {
            "id": tid,
            "title": f"Topic {cid}: {label}",
            "year": "",
            "doi": "",
            "url": "",
            "has_doi": False,
            "external": False,
            "topic": True,
            "cluster": cid,
            "degree": 0, "pagerank": None,
            "terms": (t.get("top_terms") or [])[:10],
        }
        topic_nodes.append(tn)
        id_order.append(tid)

    cluster_to_tid = {int(t.get("cluster", 0)): f"T{int(t.get('cluster', 0))}" for t in topics}
    for i, d in enumerate(docs):
        c = int(labels[i]) if labels else 0
        tid = cluster_to_tid.get(c)
        if tid:
            edges_topic_membership.append({"source": d.id, "target": tid, "weight": 1})

    nodes.extend(topic_nodes)

    # --- 7) Finish external nodes
    for rid, n in ext_nodes.items():
        votes = ext_votes.get(rid) or Counter()
        cluster = max(votes.items(), key=lambda kv: (kv[1], -kv[0]))[0] if votes else 0
        n["cluster"] = int(cluster)
        n.setdefault("degree", 0)
        n.setdefault("pagerank", None)
        n["has_doi"] = bool(n.get("doi"))
        nodes.append(n)
        id_order.append(rid)

    # --- 8) Classic edge sets
    edges_citations = doc_edges + ext_edges
    edges_mutual = _mutual_edges(doc_edges)
    edges_shared = _biblio_coupling(docs)
    edges_cocited = _co_citation(doc_edges)

    # --- 9) Semantic edges + suggested
    emb, emb_model = _embed_texts(texts)
    N = len(docs)
    knn_k = max(3, min(12, int(round(math.sqrt(max(2, N))))))
    sim_thresh = float(os.environ.get("PAPERCLIP_SIM_THRESH", "0.32"))
    edges_semantic = _knn_edges(emb, [d.id for d in docs], k=knn_k, thresh=sim_thresh)

    c_pairs = {(min(e["source"], e["target"]), max(e["source"], e["target"])) for e in doc_edges}
    suggested = []
    for e in edges_semantic:
        a, b = (e["source"], e["target"])
        key = (a, b) if a < b else (b, a)
        if key not in c_pairs:
            suggested.append({"source": a, "target": b, "weight": e.get("weight", 1)})

    # --- 10) Topic ↔ Topic relations (Jaccard on top terms)
    edges_t2t: List[Dict[str, Any]] = []
    topic_map = {int(t["cluster"]): t for t in topics}
    for a, b in combinations(sorted(topic_map.keys()), 2):
        A = set(topic_map[a].get("top_terms") or [])
        B = set(topic_map[b].get("top_terms") or [])
        if not A or not B:
            continue
        j = len(A & B) / float(len(A | B))
        if j >= 0.18:
            edges_t2t.append({"source": f"T{a}", "target": f"T{b}", "weight": max(1, int(round(j * 10)))})

    # --- 11) Metrics on citation graph
    metrics = compute_metrics(id_order, edges_citations)
    for n in nodes:
        m = metrics.get(n["id"], {})
        n["degree"] = int(m.get("degree", 0.0))
        if "pagerank" in m:
            n["pagerank"] = float(m["pagerank"])

    # --- 12) Simple gap flags
    deg_sem: Dict[str, int] = defaultdict(int)
    for e in edges_semantic:
        deg_sem[e["source"]] += 1
        deg_sem[e["target"]] += 1

    tiny_topic_cutoff = int(os.environ.get("PAPERCLIP_TINY_TOPIC", "3"))
    gaps_summary = {"topic_gaps": [], "node_gaps": []}
    cluster_counts: Dict[int, int] = Counter(int(c) for c in labels) if labels else Counter({0: len(docs)})
    tiny_clusters = {cid for cid, cnt in cluster_counts.items() if cnt < tiny_topic_cutoff}
    NodeById = {n["id"]: n for n in nodes}
    for cid in sorted(tiny_clusters):
        gaps_summary["topic_gaps"].append({"cluster": int(cid), "size": int(cluster_counts[cid])})
    for i, d in enumerate(docs):
        cid = int(labels[i]) if labels else 0
        reasons = []
        if metrics.get(d.id, {}).get("degree", 0) == 0 and deg_sem.get(d.id, 0) <= 1:
            reasons.append("isolated")
        if cid in tiny_clusters:
            reasons.append("tiny_topic")
        if reasons:
            NodeById[d.id]["gap"] = True
            NodeById[d.id]["gap_reasons"] = reasons
            gaps_summary["node_gaps"].append({"id": d.id, "reasons": reasons})

    # --- 13) Persist
    data = {
        "nodes": nodes,
        "edges": edges_citations,
        "edgesets": {
            "citations": edges_citations,
            "mutual": edges_mutual,
            "shared_refs": edges_shared,
            "co_cited": edges_cocited,
            "semantic": edges_semantic,
            "suggested": suggested,
            "topic_membership": edges_topic_membership,
            "topic_relations": edges_t2t,
        },
        "topics": topics,
        "k": (max(labels) + 1 if labels else 1),
        "mode": mode,
        "embedding_model": emb_model,
        "gaps": gaps_summary,
    }
    (out_dir / "graph.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"stats": {"docs": len(nodes), "edges": len(edges_citations)}, "k": data["k"], "mode": mode}
