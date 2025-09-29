# services/server/analysis/run_pipeline.py
from __future__ import annotations
import hashlib, json
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List
from collections import Counter, defaultdict

from .graph_build import collect_docs, build_citation_edges, compute_metrics
from .topics import select_topics
from .text import tokenize
from paperclip.utils import norm_doi


def _stable_ref_id(doi: str, title: str, year: str) -> str:
    key = (doi or "").strip().lower() or (title.strip().lower() + "|" + year.strip())
    key = key or title or "ref"
    return "x_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _mutual_edges(directed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Undirected edges where both directions exist; weight = sum of both."""
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
    """
    Undirected edges between captures weighted by the size of the intersection
    of their referenced DOIs. (Overlapping references.)
    """
    refs = {d.id: set(d.refs_doi) for d in docs}
    ids = [d.id for d in docs]
    out: List[Dict[str, Any]] = []
    for a, b in combinations(ids, 2):
        inter = refs[a] & refs[b]
        if inter:
            out.append({"source": a, "target": b, "weight": len(inter)})
    return out


def _co_citation(directed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Undirected edges between targets that are cited together by at least one capture.
    Weight = number of distinct citing captures that cite both targets.
    """
    by_src: Dict[str, set[str]] = defaultdict(set)
    for e in directed:
        by_src[e["source"]].add(e["target"])
    w = defaultdict(int)
    for s, targets in by_src.items():
        for a, b in combinations(sorted(targets), 2):
            w[(a, b)] += 1
    return [{"source": a, "target": b, "weight": c} for (a, b), c in w.items() if c > 0]


def run(out_dir: Path, k: int | None = None) -> Dict[str, Any]:
    """
    Build topics, compose nodes (captures + optional external refs), and produce
    multiple edge sets:
      - citations     (direct edges; includes external ref nodes)
      - mutual        (A⇄B only; undirected)
      - shared_refs   (bibliographic coupling: overlap count of reference DOIs)
      - co_cited      (targets cited together by a capture)
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1) Captures → documents
    docs = collect_docs()

    # --- 2) Directed capture→capture edges (by DOI)
    doc_edges = build_citation_edges(docs)

    # --- 3) Topics on capture texts
    texts = [d.text for d in docs]
    labels, topics, doc_terms_map, mode = select_topics(texts, k=k)

    # --- 4) External reference nodes + edges (uncaptured citations)
    doi_to_doc = {d.doi: d for d in docs if d.doi}
    ext_nodes: Dict[str, Dict[str, Any]] = {}                  # id → node dict
    ext_votes: Dict[str, Counter] = defaultdict(Counter)       # id → cluster votes
    ext_edges: List[Dict[str, Any]] = []

    for i, d in enumerate(docs):
        c = int(labels[i]) if labels else 0
        for r in d.refs:
            rdoi = norm_doi(r.get("doi"))
            # If the reference is already a capture, the doc_edges cover it.
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
                    # cluster/metrics filled later
                }
            ext_votes[rid][c] += 1
            ext_edges.append({"source": d.id, "target": rid, "weight": 1})

    # --- 5) Nodes (captures first, then externals)
    nodes: List[Dict[str, Any]] = []
    id_order: List[str] = []

    for i, d in enumerate(docs):
        nodes.append({
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
        })
        id_order.append(d.id)

    for rid, n in ext_nodes.items():
        # assign majority cluster of its citers
        votes = ext_votes.get(rid) or Counter()
        cluster = max(votes.items(), key=lambda kv: (kv[1], -kv[0]))[0] if votes else 0
        n["cluster"] = int(cluster)
        n.setdefault("degree", 0)
        n.setdefault("pagerank", None)
        n["has_doi"] = bool(n.get("doi"))
        nodes.append(n)
        id_order.append(rid)

    # --- 6) Edge sets
    edges_citations = doc_edges + ext_edges
    edges_mutual = _mutual_edges(doc_edges)
    edges_shared = _biblio_coupling(docs)
    edges_cocited = _co_citation(doc_edges)

    # --- 7) Metrics over the combined directed graph (citations)
    metrics = compute_metrics(id_order, edges_citations)
    for n in nodes:
        m = metrics.get(n["id"], {})
        n["degree"] = int(m.get("degree", 0.0))
        if "pagerank" in m:
            n["pagerank"] = float(m["pagerank"])

    # --- 8) Persist
    data = {
        "nodes": nodes,
        "edges": edges_citations,  # legacy field
        "edgesets": {
            "citations": edges_citations,
            "mutual": edges_mutual,
            "shared_refs": edges_shared,
            "co_cited": edges_cocited,
        },
        "topics": topics,
        "k": (max(labels) + 1 if labels else 1),
        "mode": mode,
    }
    (out_dir / "graph.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"stats": {"docs": len(nodes), "edges": len(edges_citations)}, "k": data["k"], "mode": mode}
