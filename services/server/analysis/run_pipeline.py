# services/server/analysis/run_pipeline.py
from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from contextlib import suppress
from itertools import combinations
from pathlib import Path
from typing import Any, cast

import numpy as np

from paperclip.utils import norm_doi

from .graph_build import build_citation_edges, collect_docs, compute_metrics
from .text import tokenize
from .topics import label_topics_if_configured, select_topics


# ----------------------------- helpers -----------------------------
def _stable_ref_id(doi: str, title: str, year: str) -> str:
    key = (doi or "").strip().lower() or (title.strip().lower() + "|" + year.strip())
    key = key or title or "ref"
    return "x_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _mutual_edges(directed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pair: dict[tuple[str, str], list[int]] = defaultdict(
        lambda: [0, 0]
    )  # (a<b ? [a->b, b->a] : [b->a, a->b])
    for e in directed:
        a, b, w = e["source"], e["target"], int(e.get("weight", 1))
        if a == b:
            continue
        u, v = (a, b) if a < b else (b, a)
        if a < b:
            pair[(u, v)][0] += w
        else:
            pair[(u, v)][1] += w
    out: list[dict[str, Any]] = []
    for (u, v), (ab, ba) in pair.items():
        if ab and ba:
            out.append({"source": u, "target": v, "weight": ab + ba})
    return out


def _biblio_coupling(docs) -> list[dict[str, Any]]:
    refs = {d.id: set(d.refs_doi) for d in docs}
    ids = [d.id for d in docs]
    out: list[dict[str, Any]] = []
    for a, b in combinations(ids, 2):
        inter = refs[a] & refs[b]
        if inter:
            out.append({"source": a, "target": b, "weight": len(inter)})
    return out


def _co_citation(directed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_src: dict[str, set[str]] = defaultdict(set)
    for e in directed:
        by_src[e["source"]].add(e["target"])
    w: dict[tuple[str, str], int] = defaultdict(int)
    for _s, targets in by_src.items():
        for a, b in combinations(sorted(targets), 2):
            w[(a, b)] += 1
    return [{"source": a, "target": b, "weight": c} for (a, b), c in w.items() if c > 0]


def sanitize_graph(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Ensure every edge endpoint exists in nodes. Drop and log any broken edges.
    Node objects must have 'id', edge objects 'source' and 'target'.
    Returns (nodes, edges_clean).
    """
    idset = {str(n.get("id")) for n in nodes if n.get("id") is not None}
    clean: list[dict[str, Any]] = []
    dropped = 0
    for e in edges:
        s = str(e.get("source"))
        t = str(e.get("target"))
        if s in idset and t in idset:
            clean.append(e)
        else:
            dropped += 1
    if dropped:
        with suppress(Exception):
            import logging

            logging.getLogger(__name__).warning(
                "sanitize_graph: dropped %d broken edges", dropped
            )
    return nodes, clean


def sanitize_graph_dict(graph: dict[str, Any]) -> dict[str, Any]:
    """
    Same as sanitize_graph, but works on a 'graph' dict with keys 'nodes' and 'edges'.
    Returns the same dict instance for convenience.
    """
    nodes = cast(list[dict[str, Any]], graph.get("nodes") or [])
    edges = cast(list[dict[str, Any]], graph.get("edges") or [])
    nodes, edges = sanitize_graph(nodes, edges)
    graph["nodes"] = nodes
    graph["edges"] = edges
    return graph


# ----------------------------- embeddings + semantic edges -----------------------------
def _safe_normalize_rows(M: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return M / norms


def _embed_texts(texts: list[str]) -> tuple[np.ndarray, str]:
    model_name = os.environ.get("PAPERCLIP_EMBED_MODEL", "allenai/specter2_base")
    with suppress(Exception):
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
        embs = model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(embs, dtype="float32"), model_name
    # Fallback: TF-IDF + TruncatedSVD (dense 128-dim)
    try:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(
            stop_words="english", max_features=20000, ngram_range=(1, 2), min_df=1
        )
        X = vec.fit_transform(texts)
        k = min(128, max(16, min(X.shape[0] - 1, X.shape[1] - 1)))
        svd = TruncatedSVD(n_components=k, random_state=42)
        Z = svd.fit_transform(X)
        Z = _safe_normalize_rows(np.asarray(Z, dtype="float32"))
        return Z, "tfidf-svd"
    except Exception:
        # Final fallback: bag-of-words count of tokens
        from .text import tokenize as _tok

        toks = [_tok(t) for t in texts]
        vocab: dict[str, int] = {}
        rows: list[dict[int, float]] = []
        for ts in toks:
            row: dict[int, float] = {}
            for w in ts:
                j = vocab.setdefault(w, len(vocab))
                row[j] = row.get(j, 0.0) + 1.0
            rows.append(row)
        n, d = len(texts), max(1, len(vocab))
        M = np.zeros((n, d), dtype="float32")
        for i, row in enumerate(rows):
            for j, val in row.items():
                M[i, j] = val
        M = _safe_normalize_rows(M)
        return M, "bow"


def _knn_edges(
    emb: np.ndarray, ids: list[str], *, k: int = 8, thresh: float = 0.32
) -> list[dict[str, Any]]:
    if emb.shape[0] <= 2:
        return []
    X = _safe_normalize_rows(emb.astype("float32"))
    sims = X @ X.T
    np.fill_diagonal(sims, -1.0)
    k = max(1, min(k, sims.shape[0] - 1))
    seen: set[tuple[int, int]] = set()
    edges: list[dict[str, Any]] = []
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
            w = max(1, round(sim * 100))
            edges.append({"source": ids[a], "target": ids[b], "weight": w})
    return edges


# ----------------------------- main pipeline -----------------------------
def run(out_dir: Path, k: int | None = None) -> dict[str, Any]:
    """
    Builds nodes/edges and writes graph.json into out_dir.
    Adds: semantic edges, topic nodes, topic relations, gap flags, and LLM topic labels (cached).
    Also sanitizes all edge sets to ensure every link endpoint exists in `nodes`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # --- 1) Captures → documents
    docs = collect_docs()
    if not docs:
        data = {
            "nodes": [],
            "edges": [],
            "edgesets": {},
            "topics": [],
            "k": 0,
            "mode": "empty",
        }
        (out_dir / "graph.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"stats": {"docs": 0, "edges": 0}, "k": 0, "mode": "empty"}
    # --- 2) Directed capture→capture edges (by DOI)
    doc_edges = build_citation_edges(docs)  # capture → capture only
    # --- 3) Topics on capture texts
    texts = [d.text for d in docs]
    labels, topics, doc_terms_map, mode = select_topics(texts, k=k)
    topics = label_topics_if_configured(topics, texts, labels, cache_dir=out_dir.parent)
    # --- 4) External reference nodes + edges (uncaptured citations)
    doi_to_doc = {d.doi: d for d in docs if d.doi}
    ext_nodes: dict[str, dict[str, Any]] = {}
    ext_votes: dict[str, Counter] = defaultdict(Counter)
    ext_edges: list[dict[str, Any]] = []

    def _stable_ref_id(doi: str, title: str, year: str) -> str:
        import hashlib as _h

        key = (doi or "").strip().lower() or (
            (title or "").strip().lower() + "|" + (year or "").strip()
        )
        key = key or (title or "") or "ref"
        return "x_" + _h.sha1(key.encode("utf-8")).hexdigest()[:12]

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
    nodes: list[dict[str, Any]] = []
    id_order: list[str] = []
    for i, d in enumerate(docs):
        n: dict[str, Any] = {
            "id": d.id,
            "title": d.title,
            "year": d.year,
            "doi": d.doi,
            "url": d.url,
            "has_doi": bool(d.doi),
            "external": False,
            "cluster": int(labels[i]) if labels else 0,
            "degree": 0,
            "pagerank": None,
            "terms": doc_terms_map.get(str(i), []) or tokenize(d.text)[:8],
        }
        nodes.append(n)
        id_order.append(d.id)
    # --- 6) Topic nodes + membership edges
    topic_nodes: list[dict[str, Any]] = []
    edges_topic_membership: list[dict[str, Any]] = []
    cluster_to_tid: dict[int, str] = {}
    for t in topics:
        cid = int(t.get("cluster", 0))
        label: str = cast(
            str,
            (
                t.get("label")
                or " · ".join((t.get("top_terms") or [])[:3])
                or f"Topic {cid}"
            ),
        )
        tid = f"T{cid}"
        topic_nodes.append(
            {
                "id": tid,
                "title": f"Topic {cid}: {label}",
                "year": "",
                "doi": "",
                "url": "",
                "has_doi": False,
                "external": False,
                "topic": True,
                "cluster": cid,
                "degree": 0,
                "pagerank": None,
                "terms": (t.get("top_terms") or [])[:10],
            }
        )
        cluster_to_tid[cid] = tid
        id_order.append(tid)
    for i, d in enumerate(docs):
        c = int(labels[i]) if labels else 0
        tid = cluster_to_tid.get(c)
        if tid:
            edges_topic_membership.append({"source": d.id, "target": tid, "weight": 1})
    nodes.extend(topic_nodes)
    # --- 7) Finish external nodes (assign cluster by votes)
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
    edges_doc_citations = doc_edges  # capture→capture
    edges_references = ext_edges  # capture→external
    edges_citations = edges_doc_citations + edges_references  # combined (compat)
    # symmetric/derived sets
    from itertools import combinations as _comb

    def _mutual_edges(directed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pair: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        for e in directed:
            a, b, w = e["source"], e["target"], int(e.get("weight", 1))
            if a == b:
                continue
            u, v = (a, b) if a < b else (b, a)
            if a < b:
                pair[(u, v)][0] += w
            else:
                pair[(u, v)][1] += w
        out: list[dict[str, Any]] = []
        for (u, v), (ab, ba) in pair.items():
            if ab and ba:
                out.append({"source": u, "target": v, "weight": ab + ba})
        return out

    def _biblio_coupling(docs_) -> list[dict[str, Any]]:
        refs = {d.id: set(d.refs_doi) for d in docs_}
        ids = [d.id for d in docs_]
        out: list[dict[str, Any]] = []
        for a, b in _comb(ids, 2):
            inter = refs[a] & refs[b]
            if inter:
                out.append({"source": a, "target": b, "weight": len(inter)})
        return out

    def _co_citation(directed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_src: dict[str, set[str]] = defaultdict(set)
        for e in directed:
            by_src[e["source"]].add(e["target"])
        w: dict[tuple[str, str], int] = defaultdict(int)
        for _s, targets in by_src.items():
            for a, b in _comb(sorted(targets), 2):
                w[(a, b)] += 1
        return [
            {"source": a, "target": b, "weight": c} for (a, b), c in w.items() if c > 0
        ]

    edges_mutual = _mutual_edges(edges_doc_citations)
    edges_shared = _biblio_coupling(docs)
    edges_cocited = _co_citation(edges_doc_citations)

    # --- 9) Semantic edges + suggested
    def _safe_normalize_rows(M: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(M, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return M / norms

    def _embed_texts(texts: list[str]) -> tuple[np.ndarray, str]:
        model_name = os.environ.get("PAPERCLIP_EMBED_MODEL", "allenai/specter2_base")
        with suppress(Exception):
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
            embs = model.encode(
                texts,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return np.asarray(embs, dtype="float32"), model_name
        try:
            from sklearn.decomposition import TruncatedSVD
            from sklearn.feature_extraction.text import TfidfVectorizer

            vec = TfidfVectorizer(
                stop_words="english", max_features=20000, ngram_range=(1, 2), min_df=1
            )
            X = vec.fit_transform(texts)
            kdim = min(128, max(16, min(X.shape[0] - 1, X.shape[1] - 1)))
            svd = TruncatedSVD(n_components=kdim, random_state=42)
            Z = _safe_normalize_rows(np.asarray(svd.fit_transform(X), dtype="float32"))
            return Z, "tfidf-svd"
        except Exception:
            toks = [tokenize(t) for t in texts]
            vocab: dict[str, int] = {}
            rows: list[dict[int, float]] = []
            for ts in toks:
                row: dict[int, float] = {}
                for w in ts:
                    j = vocab.setdefault(w, len(vocab))
                    row[j] = row.get(j, 0.0) + 1.0
                rows.append(row)
            n, d = len(texts), max(1, len(vocab))
            M = np.zeros((n, d), dtype="float32")
            for i, row in enumerate(rows):
                for j, val in row.items():
                    M[i, j] = val
            M = _safe_normalize_rows(M)
            return M, "bow"

    def _knn_edges(
        emb: np.ndarray, ids: list[str], *, k: int = 8, thresh: float = 0.32
    ) -> list[dict[str, Any]]:
        if emb.shape[0] <= 2:
            return []
        X = _safe_normalize_rows(emb.astype("float32"))
        sims = X @ X.T
        np.fill_diagonal(sims, -1.0)
        k = max(1, min(k, sims.shape[0] - 1))
        seen: set[tuple[int, int]] = set()
        edges: list[dict[str, Any]] = []
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
                w = max(1, round(sim * 100))
                edges.append({"source": ids[a], "target": ids[b], "weight": w})
        return edges

    emb, emb_model = _embed_texts(texts)
    N = len(docs)
    knn_k = max(3, min(12, round(math.sqrt(max(2, N)))))
    sim_thresh = float(os.environ.get("PAPERCLIP_SIM_THRESH", "0.32"))
    edges_semantic = _knn_edges(emb, [d.id for d in docs], k=knn_k, thresh=sim_thresh)
    c_pairs = {
        (min(e["source"], e["target"]), max(e["source"], e["target"]))
        for e in edges_doc_citations
    }
    suggested: list[dict[str, Any]] = []
    for e in edges_semantic:
        a, b = (e["source"], e["target"])
        key = (a, b) if a < b else (b, a)
        if key not in c_pairs:
            suggested.append({"source": a, "target": b, "weight": e.get("weight", 1)})
    # --- 10) Topic ↔ Topic relations (Jaccard on top terms)
    edges_t2t: list[dict[str, Any]] = []
    topic_map = {int(t["cluster"]): t for t in topics}
    from itertools import combinations as _comb2

    for a, b in _comb2(sorted(topic_map.keys()), 2):
        A = set(topic_map[a].get("top_terms") or [])
        B = set(topic_map[b].get("top_terms") or [])
        if not A or not B:
            continue
        j = len(A & B) / float(len(A | B))
        if j >= 0.18:
            edges_t2t.append(
                {"source": f"T{a}", "target": f"T{b}", "weight": max(1, round(j * 10))}
            )
    # --- 10.5) SANITIZE: drop any edges pointing to missing nodes (all sets)
    from .graph_utils import sanitize_graph as _sg

    def _clean(arr: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _sg(nodes, arr)[1]

    edges_doc_citations = _clean(edges_doc_citations)
    edges_references = _clean(edges_references)
    edges_citations = _clean(edges_citations)
    edges_mutual = _clean(edges_mutual)
    edges_shared = _clean(edges_shared)
    edges_cocited = _clean(edges_cocited)
    edges_semantic = _clean(edges_semantic)
    suggested = _clean(suggested)
    edges_topic_membership = _clean(edges_topic_membership)
    edges_t2t = _clean(edges_t2t)
    # --- 11) Metrics on citation graph
    metrics: dict[str, dict[str, float]] = compute_metrics(id_order, edges_citations)
    for n in nodes:
        # Ensure key is str, and provide a typed fallback to appease mypy
        key = str(n.get("id", ""))
        m = metrics.get(key) or cast(dict[str, float], {})
        n["degree"] = int(m.get("degree", 0.0))
        if "pagerank" in m:
            n["pagerank"] = float(m["pagerank"])
    # --- 12) Simple gap flags
    deg_sem: dict[str, int] = defaultdict(int)
    for e in edges_semantic:
        deg_sem[e["source"]] += 1
        deg_sem[e["target"]] += 1
    tiny_topic_cutoff = int(os.environ.get("PAPERCLIP_TINY_TOPIC", "3"))
    gaps_summary: dict[str, list[dict[str, Any]]] = {"topic_gaps": [], "node_gaps": []}
    cluster_counts: dict[int, int] = (
        Counter(int(c) for c in labels) if labels else Counter({0: len(docs)})
    )
    tiny_clusters = {
        cid for cid, cnt in cluster_counts.items() if cnt < tiny_topic_cutoff
    }
    NodeById = {n["id"]: n for n in nodes}
    for cid in sorted(tiny_clusters):
        gaps_summary["topic_gaps"].append(
            {"cluster": int(cid), "size": int(cluster_counts[cid])}
        )
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
    data: dict[str, Any] = {
        "nodes": nodes,
        "edges": edges_citations,
        "edgesets": {
            "doc_citations": edges_doc_citations,
            "references": edges_references,
            "citations": edges_citations,  # combined (compat)
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
    (out_dir / "graph.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "stats": {"docs": len(nodes), "edges": len(edges_citations)},
        "k": data["k"],
        "mode": mode,
    }
