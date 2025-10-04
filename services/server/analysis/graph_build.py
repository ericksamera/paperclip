# services/server/analysis/graph_build.py
from __future__ import annotations

from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from captures.models import Capture
from captures.reduced_view import read_reduced_view
from paperclip.utils import norm_doi


@dataclass
class Doc:
    id: str
    title: str
    year: str
    doi: str
    url: str
    text: str
    refs_doi: list[str]
    refs: list[dict[str, Any]]


def collect_docs() -> list[Doc]:
    docs: list[Doc] = []
    for c in Capture.objects.all().order_by("-created_at"):
        view = read_reduced_view(str(c.id))
        sections = view.get("sections") or {}
        paras = sections.get("abstract_or_body") or []
        parts: list[str] = []
        if c.title:
            parts.append(str(c.title))
        meta = c.meta if isinstance(c.meta, dict) else {}
        csl = c.csl if isinstance(c.csl, dict) else {}
        if meta.get("abstract"):
            parts.append(str(meta["abstract"]))
        elif csl.get("abstract"):
            parts.append(str(csl["abstract"]))
        if paras:
            parts.append(" ".join(paras))
        kws = meta.get("keywords") or []
        if isinstance(kws, list) and kws:
            parts.append(" ".join([str(k) for k in kws]))
        refs_list: list[dict[str, Any]] = []
        refs_doi: list[str] = []
        vrefs = view.get("references") or []
        if vrefs:
            for r in vrefs:
                d = norm_doi((r or {}).get("doi"))
                t = (r or {}).get("title") or ""
                y = str((r or {}).get("issued_year") or "")
                refs_list.append({"doi": d, "title": t, "issued_year": y})
                if d:
                    refs_doi.append(d)
        else:
            for r in c.references.all().only("doi", "title", "issued_year"):
                d = norm_doi(getattr(r, "doi", ""))
                t = getattr(r, "title", "") or ""
                y = str(getattr(r, "issued_year", "") or "")
                refs_list.append({"doi": d, "title": t, "issued_year": y})
                if d:
                    refs_doi.append(d)
        docs.append(
            Doc(
                id=str(c.id),
                title=c.title or "",
                year=c.year or "",
                doi=c.doi or "",
                url=c.url or "",
                text=" ".join(parts),
                refs_doi=refs_doi,
                refs=refs_list,
            )
        )
    return docs


def build_citation_edges(docs: list[Doc]) -> list[dict[str, Any]]:
    """Edges only between captures that both exist in the library (DOI match)."""
    doi_to_id = {d.doi: d.id for d in docs if d.doi}
    weights: dict[tuple[str, str], int] = defaultdict(int)
    for d in docs:
        for rdoi in d.refs_doi:
            tgt = doi_to_id.get(rdoi)
            if tgt and tgt != d.id:
                weights[(d.id, tgt)] += 1
    return [{"source": s, "target": t, "weight": w} for (s, t), w in weights.items()]


def compute_metrics(nodes: list[str], edges: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """
    Returns: metrics[id] = {"degree": deg, "pagerank": pr?}
    """
    deg: dict[str, float] = defaultdict(float)
    for e in edges:
        deg[e["source"]] += e.get("weight", 1.0)
        deg[e["target"]] += e.get("weight", 1.0)
    out = {nid: {"degree": float(deg.get(nid, 0.0))} for nid in nodes}
    with suppress(Exception):
        import networkx as nx  # optional

        G = nx.DiGraph()
        G.add_nodes_from(nodes)
        for e in edges:
            G.add_edge(e["source"], e["target"], weight=float(e.get("weight", 1.0)))
        pr = nx.pagerank(G, alpha=0.85, weight="weight")
        for nid, val in pr.items():
            out.setdefault(nid, {})["pagerank"] = float(val)
    return out
