from __future__ import annotations
import argparse, json
from pathlib import Path

from .io import load_docs
from .embeddings import compute_embeddings
from .cluster import kmeans_labels
from .graph_build import build_graph
from .themes import label_clusters
from .recommend import recommend_next
from .bib import aggregate_bib
from .utils import safe_json
from .vis import write_graph_html


def main():
    ap = argparse.ArgumentParser(
        description="Paperclip miner: cluster + graph + themes + references + recs"
    )
    ap.add_argument(
        "--in", dest="inputs", nargs="+", required=True,
        help='Input JSON globs (e.g., "artifacts/*/server_parsed.json")'
    )
    ap.add_argument("--out", dest="outdir", required=True, help="Output directory")
    ap.add_argument("--k", dest="k", type=int, default=None,
                    help="Number of clusters; if omitted, auto-select")
    ap.add_argument("--knn", dest="knn", type=int, default=7,
                    help="k for k-NN similarity edges (default 7)")
    ap.add_argument("--topn", dest="topn", type=int, default=20,
                    help="Top-N recommendations to output (default 20)")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # 1) Load docs
    docs = load_docs(args.inputs)
    if not docs:
        raise SystemExit("No documents found. Check your --in glob(s).")

    # 2) Embeddings
    X, _payload = compute_embeddings(docs)  # X: (n, d) ndarray

    # 3) Clustering
    labels, compact = kmeans_labels(X, k=args.k)

    # 4) Graph
    graph, degree = build_graph(docs, X, labels, k_sim=args.knn)
    safe_json(graph, outdir / "graph.json")

    # 5) Themes (themes = {clusterId: {label, top_terms, size, ...}})
    themes, doc_themes = label_clusters(docs, labels)
    safe_json({"themes": themes, "docThemes": doc_themes}, outdir / "themes.json")

    # 6) Recommendations
    recs = recommend_next(docs, labels, degree, top_n=args.topn)
    safe_json({"recommendations": recs}, outdir / "recommendations.json")

    # 7) Aggregate BibTeX
    (outdir / "references.bib").write_text(aggregate_bib(docs), "utf-8")

    # 8) Self-contained, offline viewer (graph + themes inlined)
    write_graph_html(graph, themes, outdir / "graph.html")

    # 9) Echo a small summary (stdout)
    summary = {
        "n_docs": len(docs),
        "k": int(len(set(int(x) for x in labels))) if len(labels) else 0,
        "compactness": float(compact),
        "graph_nodes": len(graph.get("nodes", [])),
        "graph_edges": len(graph.get("edges", [])),
        "themes": len(themes),
        "top_recs": len(recs),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
