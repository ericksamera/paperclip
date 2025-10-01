// Graph module with controls. Exposes window.PCGraph.{bootGraph,bootGraphWithData,view}.

import * as Hull from "./hulls.js";
import * as Edges from "./edges.js";
import * as Layout from "./layout.js";
import { initControls } from "./controls.js";

async function ensureD3() {
  if (window.d3) return;
  await new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/d3@7";
    s.onload = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

function availableEdgeKeys(graph) {
  const pref = ["doc_citations","citations","references","semantic","suggested","mutual","shared_refs","co_cited","topic_relations","topic_membership"];
  const keys = graph.edgesets ? Object.keys(graph.edgesets) : [];
  const out = [];
  for (const k of pref) if (keys.includes(k)) out.push(k);
  for (const k of keys) if (!out.includes(k)) out.push(k);
  if (!out.length && graph.edges) out.push("edges");
  return out;
}
function defaultEdgeKey(graph) {
  const avail = availableEdgeKeys(graph);
  if (avail.includes("doc_citations")) return "doc_citations";
  if (avail.includes("citations"))     return "citations";
  return avail[0] || "edges";
}

// Pleasant, stable palette (Tableau-ish). We modulo by length.
const PALETTE = [
  "#60a5fa","#34d399","#f472b6","#f59e0b","#a78bfa","#22d3ee",
  "#f87171","#10b981","#facc15","#ef4444","#84cc16","#06b6d4"
];
function colorForCluster(cid) {
  const i = Math.abs(parseInt(cid ?? 0, 10)) % PALETTE.length;
  return PALETTE[i];
}

class GraphView {
  constructor(root, graph) {
    this.root = root;
    this.graph = graph;

    this.edgeKey = defaultEdgeKey(graph);
    this.includeExternal = this._defaultIncludeExternalFor(this.edgeKey);
    this.showHulls = true;
    this.linkDistance = 48;
    this.charge = -45;
    this.collision = 8;
    this.paused = false;

    this.w = Math.max(600, root.clientWidth || 900);
    this.h = Math.max(400, root.clientHeight || 600);

    this.svg    = d3.select(root).append("svg").attr("width", this.w).attr("height", this.h);
    this.gEdges = this.svg.append("g").attr("class", "g-edges");
    this.gHulls = this.svg.append("g").attr("class", "g-hulls");
    this.gNodes = this.svg.append("g").attr("class", "g-nodes");

    this.nodes = (graph.nodes || []).map(n => ({ ...n }));
    this.nodeIndex = new Map(this.nodes.map(n => [String(n.id), n])); // id → node

    Layout.fitToViewport(this.nodes, this.w, this.h, 24);

    this.edges = this._edgesForCurrent();
    // If chosen set is thin/empty, auto-fallback to something that actually shows structure.
    this._autoFallbackWhenSparse();

    this.sim = Layout.createSimulation(this.nodes, this.edges, {
      width: this.w, height: this.h,
      linkDistance: this.linkDistance, charge: this.charge, collision: this.collision,
    });

    this.linkSel = this.gEdges.selectAll("line.edge")
      .data(this.edges, d => String(this._idOf(d.source)) + "→" + String(this._idOf(d.target)))
      .enter().append("line")
      .attr("class", "edge")
      .attr("stroke", "#444")
      .attr("stroke-opacity", 0.6)
      .attr("vector-effect", "non-scaling-stroke")
      .attr("stroke-width", e => Math.max(1, Math.sqrt(e.weight || 1)));

    this.nodeSel = this.gNodes.selectAll("g.node")
      .data(this.nodes, d => d.id)
      .enter().append("g")
      .attr("class", "node");

    // Colored nodes by cluster; topic nodes slightly larger; external nodes have outline.
    this.nodeSel.append("circle")
      .attr("r", d => (d.topic ? 6 : 4))
      .attr("fill", d => colorForCluster(d.cluster ?? 0))
      .attr("fill-opacity", d => (d.external ? 0.75 : 1))
      .attr("stroke", d => (d.external ? colorForCluster(d.cluster ?? 0) : "#000"))
      .attr("stroke-opacity", d => (d.external ? 0.7 : 0.25));

    this.nodeSel.append("title").text(d => d.title || d.id);

    this._updateVisible();

    this.sim.on("tick", () => this.render());
    this.render();
  }

  // ---------- edge & node visibility helpers ----------
  _defaultIncludeExternalFor(key) {
    if (key === "doc_citations" || key === "citations") return false;
    if (key === "references") return true;
    return true;
  }
  _idOf(v) { return (v && typeof v === "object") ? (v.id ?? v) : v; }
  _isExternal(idish) {
    const id = String(this._idOf(idish));
    return !!this.nodeIndex.get(id)?.external;
  }
  _edgesOf(key) {
    const es = this.graph.edgesets || {};
    return (es[key] || []);
  }
  _edgesForCurrent() {
    const base = Edges.edgesOfType(this.graph, this.edgeKey);
    if (!base || !base.length) return [];
    if (!this.includeExternal && (this.edgeKey === "doc_citations" || this.edgeKey === "citations")) {
      return base.filter(e => !this._isExternal(e.source) && !this._isExternal(e.target));
    }
    return base;
  }

  _autoFallbackWhenSparse() {
    // If there are 0–1 links in the current set, prefer something richer so the graph doesn't look "dead".
    const count = this.edges.length;
    const refs = this._edgesOf("references") || [];
    const sem  = this._edgesOf("semantic")   || [];
    const cits = this._edgesOf("citations")  || [];
    if (count === 0 && refs.length) {
      this.edgeKey = "references"; this.includeExternal = true; this.edges = this._edgesForCurrent();
    } else if (count <= 1 && cits.length) {
      this.edgeKey = "citations"; this.includeExternal = true; this.edges = this._edgesForCurrent();
    } else if (count <= 1 && sem.length) {
      this.edgeKey = "semantic"; this.includeExternal = true; this.edges = this._edgesForCurrent();
    }
    if (!this.edges.length) {
      this.visibleIds = new Set(this.nodes.map(n => String(n.id)));
    }
  }

  _updateVisible() {
    if (!this.edges.length) {
      this.visibleIds = new Set(this.nodes.map(n => String(n.id)));
    } else {
      const S = new Set();
      for (const e of this.edges) {
        S.add(String(this._idOf(e.source)));
        S.add(String(this._idOf(e.target)));
      }
      this.visibleIds = S;
    }
    this.nodeSel.attr("display", d => (this.visibleIds.has(String(d.id)) ? null : "none"));
  }

  // ---------- render ----------
  render() {
    this.linkSel
      .attr("x1", d => (d.source?.x ?? 0))
      .attr("y1", d => (d.source?.y ?? 0))
      .attr("x2", d => (d.target?.x ?? 0))
      .attr("y2", d => (d.target?.y ?? 0));

    this.nodeSel.attr("transform", d => `translate(${d.x ?? 0},${d.y ?? 0})`);

    if (this.showHulls) {
      const byCluster = new Map();
      for (const n of this.nodes) {
        if (!this.visibleIds || !this.visibleIds.has(String(n.id))) continue;
        const c = n.cluster ?? 0;
        if (!byCluster.has(c)) byCluster.set(c, []);
        byCluster.get(c).push(n);
      }
      const hulls = Array.from(byCluster.entries()).map(([cluster, members]) => ({
        cluster, path: Hull.clusterHullPath(members, 26), color: colorForCluster(cluster),
      }));
      const hullSel = this.gHulls.selectAll("path.hull").data(hulls, d => d.cluster);
      hullSel.enter().append("path")
        .attr("class", "hull")
        .attr("fill-opacity", 0.08)
        .attr("stroke-opacity", 0.35)
        .merge(hullSel)
        .attr("d", d => d.path)
        .attr("stroke", d => d.color)
        .attr("fill", d => d.color);
      hullSel.exit().remove();
      this.gHulls.attr("display", null);
    } else {
      this.gHulls.attr("display", "none");
    }
  }

  // ---------- controls API ----------
  setEdgeSet(key) {
    if (!key) return;
    this.edgeKey = key;
    this.includeExternal = this._defaultIncludeExternalFor(key);
    this.edges = this._edgesForCurrent();
    this._autoFallbackWhenSparse();

    this.linkSel = this.gEdges.selectAll("line.edge")
      .data(this.edges, d => String(this._idOf(d.source)) + "→" + String(this._idOf(d.target)));
    this.linkSel.exit().remove();
    this.linkSel = this.linkSel.enter().append("line")
      .attr("class", "edge")
      .attr("stroke", "#444")
      .attr("stroke-opacity", 0.6)
      .attr("vector-effect", "non-scaling-stroke")
      .attr("stroke-width", e => Math.max(1, Math.sqrt(e.weight || 1)))
      .merge(this.linkSel);

    const f = this.sim.force("link");
    f.links(this.edges).distance(this.linkDistance);

    this._updateVisible();
    this.fit();
  }

  setIncludeExternal(flag) {
    this.includeExternal = !!flag;
    this.setEdgeSet(this.edgeKey);
  }

  setHulls(flag) { this.showHulls = !!flag; this.render(); }
  setCharge(v)   { this.charge = Number(v); this.sim.force("charge").strength(this.charge); this.kick(); }
  setLinkDistance(v){ this.linkDistance = Number(v); this.sim.force("link").distance(this.linkDistance); this.kick(); }
  setCollision(v){ this.collision = Number(v); const f = this.sim.force("collide"); if (f && typeof f.radius === "function") f.radius(this.collision); this.kick(); }

  fit()  { Layout.fitToViewport(this.nodes, this.w, this.h, 24); this.kick(); }
  pause(flag){ const want = flag === undefined ? !this.paused : !!flag; this.paused = want; if (this.paused) this.sim.stop(); else this.sim.alpha(0.7).restart(); return this.paused; }
  kick() { if (!this.paused) this.sim.alpha(0.7).restart(); this.render(); }

  edgesAvailable() { return availableEdgeKeys(this.graph); }

  // Legend data for the controls
  clustersInfo() {
    // Count visible doc nodes per cluster; label via topics if present.
    const counts = new Map();
    for (const n of this.nodes) {
      if (n.topic) continue;
      const cid = Number(n.cluster ?? 0);
      counts.set(cid, (counts.get(cid) || 0) + 1);
    }
    const labelOf = (cid) => {
      const t = (this.graph.topics || []).find(t => Number(t.cluster ?? 0) === cid);
      return (t && (t.label || ("Topic " + cid))) || ("Cluster " + cid);
    };
    const out = Array.from(counts.entries())
      .map(([cid, size]) => ({ id: cid, size, label: labelOf(cid), color: colorForCluster(cid) }))
      .sort((a, b) => b.size - a.size);
    return out;
  }
}

async function renderGraph(root, graph) {
  await ensureD3();
  root.innerHTML = "";
  const view = new GraphView(root, graph);
  initControls(view);
  window.PCGraph = window.PCGraph || {};
  window.PCGraph.view = view;
  return view;
}

async function bootGraph() {
  let root = document.getElementById("graph-root");
  if (window.GRAPH_DATA && !root) {
    root = document.createElement("div");
    root.id = "graph-root";
    root.style.cssText = "width:100%;height:100vh";
    document.body.innerHTML = "";
    document.body.appendChild(root);
    await renderGraph(root, window.GRAPH_DATA);
    return;
  }
  if (root) {
    const url = root.dataset.graphUrl || "/analysis/graph.json";
    const r = await fetch(url, { credentials: "same-origin" });
    const graph = await r.json();
    await renderGraph(root, graph);
  }
}

async function bootGraphWithData(graph) {
  let root = document.getElementById("graph-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "graph-root";
    root.style.cssText = "width:100%;height:100vh";
    document.body.appendChild(root);
  }
  await renderGraph(root, graph);
}

// Public API
const NS = (window.PCGraph = window.PCGraph || {});
NS.renderGraph = renderGraph; NS.bootGraph = bootGraph; NS.bootGraphWithData = bootGraphWithData;
export { renderGraph, bootGraph, bootGraphWithData };
