from __future__ import annotations
import time
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from analysis.models import AnalysisRun

class Command(BaseCommand):
    help = "PaperClip miner: embeddings → clusters → graph → themes → recs → BibTeX → graph.html"

    def add_arguments(self, p):
        p.add_argument("--edge-mode", choices=["knn","citation","both"], default="knn")
        p.add_argument("--embedding-mode", choices=["tfidf","transformer"], default="tfidf")
        p.add_argument("--transformer-model", default="sentence-transformers/all-MiniLM-L6-v2")
        p.add_argument("--transformer-batch-size", type=int, default=32)
        p.add_argument("--abstract-only", action="store_true")
        p.add_argument("--k", type=int, default=None)
        p.add_argument("--auto-k", action="store_true")
        p.add_argument("--knn", type=int, default=7)
        p.add_argument("--topn", type=int, default=20)
        p.add_argument("--csv", default=None)

    def handle(self, *args, **o):
        ts = time.strftime("%Y%m%d-%H%M%S")
        outdir = Path(settings.ARTIFACTS_DIR) / "__runs" / ts
        outdir.mkdir(parents=True, exist_ok=True)

        # Import heavy deps lazily so missing libs don't crash the server
        try:
            from libs.paperclip_miner.io import load_documents
            from libs.paperclip_miner.embeddings import compute_embeddings
            from libs.paperclip_miner.cluster import kmeans_labels, auto_k_silhouette
            from libs.paperclip_miner.graph_build import build_graph
            from libs.paperclip_miner.themes import label_clusters
            from libs.paperclip_miner.recommend import recommend_next, write_reading_plan_csv
            from libs.paperclip_miner.bib import aggregate_bib
            from libs.paperclip_miner.utils import safe_json
            from libs.paperclip_miner.vis import write_graph_html
        except Exception as e:
            AnalysisRun.objects.create(out_dir=str(outdir), status="error", log=f"Missing libs.paperclip_miner: {e}")
            self.stderr.write(self.style.ERROR(f"Analysis aborted: {e}"))
            return

        artifacts = Path(settings.ARTIFACTS_DIR)
        in_glob = str(artifacts / "*/server_parsed.json")

        docs = load_documents([in_glob])
        if not docs:
            AnalysisRun.objects.create(out_dir=str(outdir), status="empty", log="No documents found.")
            self.stdout.write("No documents found.")
            return

        X, payload = compute_embeddings(
            docs, mode=o["embedding_mode"],
            transformer_model=o["transformer_model"],
            transformer_batch_size=o["transformer_batch_size"],
            include_fulltext=not o["abstract_only"],
        )
        if payload: safe_json(payload.to_metadata(), outdir / "embedding_artifacts.json")

        k = o["k"] if o["k"] is not None else (auto_k_silhouette(X) if o["auto_k"] else None)
        labels, compact = kmeans_labels(X, k=k)

        graph, degree = build_graph(docs, X, labels, k_sim=o["knn"], edge_mode=o["edge_mode"])
        safe_json(graph, outdir / "graph.json")

        themes, doc_themes = label_clusters(docs, labels)
        safe_json({"themes": themes, "docThemes": doc_themes}, outdir / "themes.json")

        recs = recommend_next(docs, labels, degree, top_n=o["topn"])
        safe_json({"recommendations": recs}, outdir / "recommendations.json")

        (outdir / "references.bib").write_text(aggregate_bib(docs), encoding="utf-8")
        if o["csv"]:
            p_csv = Path(o["csv"])
            if not p_csv.is_absolute():
                p_csv = outdir / p_csv
            write_reading_plan_csv(docs, degree, labels, X, str(p_csv))

        write_graph_html(graph, themes, outdir / "graph.html")

        AnalysisRun.objects.create(out_dir=str(outdir), status="done")
        self.stdout.write(self.style.SUCCESS(f"Analysis complete → {outdir}"))
