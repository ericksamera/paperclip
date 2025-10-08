from __future__ import annotations
from typing import Any


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
    for e in edges:
        s = str(e.get("source"))
        t = str(e.get("target"))
        if s in idset and t in idset:
            clean.append(e)
    return nodes, clean


def sanitize_graph_dict(graph: dict[str, Any]) -> dict[str, Any]:
    """
    Same as sanitize_graph, but works on a 'graph' dict with keys 'nodes' and 'edges'.
    Returns the same dict instance for convenience.
    """
    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    nodes, edges = sanitize_graph(nodes, edges)
    graph["nodes"] = nodes
    graph["edges"] = edges
    return graph
