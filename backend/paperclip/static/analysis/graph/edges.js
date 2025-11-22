// Small helpers for working with edge sets.

export function edgesOfType(graph, key) {
  if (!graph) return [];
  if (key && graph.edgesets && graph.edgesets[key]) return graph.edgesets[key];
  return graph.edges || [];
}

export function coalesceUndirected(edges) {
  const map = new Map();
  for (const e of edges) {
    const a = String(e.source), b = String(e.target);
    const [u, v] = a < b ? [a, b] : [b, a];
    const k = u + "→" + v;
    map.set(k, (map.get(k) || 0) + (e.weight || 1));
  }
  return Array.from(map.entries()).map(([k, w]) => {
    const [u, v] = k.split("→");
    return { source: u, target: v, weight: w };
  });
}

export function degreeMap(nodes, edges) {
  const m = new Map(nodes.map(n => [String(n.id), 0]));
  for (const e of edges) {
    if (m.has(String(e.source))) m.set(String(e.source), (m.get(String(e.source)) || 0) + 1);
    if (m.has(String(e.target))) m.set(String(e.target), (m.get(String(e.target)) || 0) + 1);
  }
  return m;
}

export function filterEdgesForNodes(edges, nodeIds) {
  const S = new Set(nodeIds.map(String));
  return edges.filter(e => S.has(String(e.source)) && S.has(String(e.target)));
}
