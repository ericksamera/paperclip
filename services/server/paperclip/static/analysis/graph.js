(function () {
  const DATA = window.GRAPH_DATA || {nodes:[], edges:[], topics:[], edgesets:null, mode:""};
  const EDGESETS = DATA.edgesets || { citations: DATA.edges || [] };
  const COLORS = ["#60a5fa","#f97316","#10b981","#a78bfa","#f43f5e","#f59e0b","#22d3ee","#84cc16","#e879f9","#38bdf8","#34d399","#eab308"];
  const byId = new Map(DATA.nodes.map(n => [n.id, n]));

  // DOM
  const svg = document.getElementById('svg');
  const scene = document.getElementById('scene');
  const hullsG = document.getElementById('hulls');
  const edgesG = document.getElementById('edges');
  const nodesG = document.getElementById('nodes');
  const labelsG = document.getElementById('clabels');

  const sizeBySel    = document.getElementById('sizeBy');
  const sizeScaleEl  = document.getElementById('sizeScale');
  const sizeScaleVal = document.getElementById('sizeScaleVal');
  const hullStyleSel = document.getElementById('hullStyle');
  const chkRefs      = document.getElementById('chkRefs');
  const edgeModeSel  = document.getElementById('edgeMode');
  const minWEl       = document.getElementById('minW');
  const minWVal      = document.getElementById('minWVal');
  const onlyDoiEl    = document.getElementById('onlyDoi');
  const hideIsoEl    = document.getElementById('hideIso');
  const nCompEl      = document.getElementById('nComp');
  const btnConnect   = document.getElementById('btnConnect');
  const chkGaps      = document.getElementById('chkGaps');
  const edgeOpacityEl= document.getElementById('edgeOpacity');
  const edgeOpacityVal = document.getElementById('edgeOpacityVal');

  document.getElementById('nDocs').textContent   = DATA.nodes.length;
  document.getElementById('nEdges').textContent  = (EDGESETS.citations || []).length;
  document.getElementById('nClus').textContent   = new Set(DATA.nodes.map(n=>n.cluster)).size;
  document.getElementById('modeVal').textContent = DATA.mode || "kmeans";

  // ---------- Topics side ----------
  let selectedCluster = null;

  function clusterLabel(t){
    if (!t) return "";
    if (t.label) return t.label;
    const words = (t.top_terms||[]).slice(0,3).join(" · ");
    return words || `Cluster ${t.cluster}`;
  }

  function renderTopics(){
    const host = document.getElementById('topics');
    host.innerHTML = (DATA.topics||[])
      .sort((a,b)=>a.cluster-b.cluster)
      .map(t => {
        const c = COLORS[t.cluster % COLORS.length];
        const chips = (t.top_terms||[]).slice(0,6).map(w => `<span class="chip" style="border-color:${c};color:${c}">${w}</span>`).join("");
        const pct = Math.round(100 * (t.size / Math.max(1, DATA.nodes.length)));
        const label = clusterLabel(t);
        const sel = (selectedCluster===t.cluster) ? 'outline:2px solid currentColor' : '';
        return `<div data-cluster="${t.cluster}" class="topic-cluster" style="margin-bottom:10px; cursor:pointer; ${sel}">
          <div style="display:flex;align-items:center;gap:8px; margin-bottom:4px">
            <span class="chip" style="background:${c}22; border-color:${c}55; color:${c}">${label}</span>
            <span class="muted">#${t.cluster} · ${t.size} docs</span>
          </div>
          <div class="bar"><span style="width:${pct}%; background:${c}"></span></div>
          <div style="margin-top:6px">${chips}</div>
        </div>`;
      }).join("");
    host.onclick = (e) => {
      const el = e.target.closest('.topic-cluster'); if(!el) return;
      const cid = Number(el.dataset.cluster);
      selectCluster(cid);
    };
  }

  function topPapersForCluster(cid, k=5){
    // rank by PageRank (then degree), ignore externals
    const list = DATA.nodes.filter(n => !n.external && !n.topic && n.cluster===cid);
    const hasPR = list.some(n => typeof n.pagerank === "number");
    list.sort((a,b) => {
      const ap = hasPR ? (a.pagerank||0) : (a.degree||0);
      const bp = hasPR ? (b.pagerank||0) : (b.degree||0);
      return bp - ap || (b.degree||0) - (a.degree||0);
    });
    return list.slice(0,k);
  }

  function renderTopicDetail(cid){
    const box = document.getElementById('topicDetail');
    const t = (DATA.topics||[]).find(x => x.cluster===cid);
    if (!t){ box.textContent = "No cluster selected."; return; }
    const c = COLORS[cid % COLORS.length];
    const top = topPapersForCluster(cid, 6);
    if (!top.length){
      box.innerHTML = `<span class="muted">No papers in this cluster.</span>`;
      return;
    }
    const terms = (t.top_terms||[]).slice(0,8).map(w => `<span class="chip" style="border-color:${c};color:${c}">${w}</span>`).join(" ");
    const items = top.map(n => {
      const short = (n.title.length > 88) ? (n.title.slice(0,85) + "…") : n.title;
      const score = (typeof n.pagerank==="number" ? `PR ${n.pagerank.toFixed(3)}` : `deg ${n.degree||0}`);
      return `<li><a href="/captures/${n.id}/" target="_blank">${short}</a> <span class="muted">· ${score}</span></li>`;
    }).join("");
    box.innerHTML = `
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
        <span class="chip" style="background:${c}22;border-color:${c}55;color:${c}">${clusterLabel(t)}</span>
        <span class="muted">#${cid} · ${t.size} docs</span>
      </div>
      <div style="margin-bottom:6px">${terms}</div>
      <ol style="padding-left:18px;margin:0">${items}</ol>
    `;
  }

  function selectCluster(cid){
    selectedCluster = cid;
    renderTopics();
    spotlightCluster(cid);
    renderTopicDetail(cid);
  }

  renderTopics();

  // ---------- Layout ----------
  function ringsLayout(){
    const W=1200, H=800, cx=W/2, cy=H/2;
    const clusters = [...new Set(DATA.nodes.map(n=>n.cluster))].sort((a,b)=>a-b);
    const R = Math.min(W,H) * 0.36;
    const centers = new Map();
    clusters.forEach((c,i) => {
      const ang = (i / Math.max(1,clusters.length)) * Math.PI*2 - Math.PI/2;
      centers.set(c, {x: cx + Math.cos(ang)*R, y: cy + Math.sin(ang)*R});
    });
    const grouped = new Map();
    DATA.nodes.forEach(n => { (grouped.get(n.cluster) || grouped.set(n.cluster, []).get(n.cluster)).push(n); });
    grouped.forEach((arr, c) => {
      const cen = centers.get(c);
      arr.forEach((n, idx) => {
        const a = (idx / Math.max(1,arr.length)) * Math.PI * 2;
        const r = 90 + (idx % Math.max(1, arr.length)) / Math.max(1, arr.length) * 100;
        n.x = (n.x ?? (cen.x + Math.cos(a)*r));
        n.y = (n.y ?? (cen.y + Math.sin(a)*r));
      });
    });
  }

  const LAYOUT_KEY = "pc-layout-" + (() => { const ids = DATA.nodes.map(n=>n.id).join(""); let h=5381; for (let i=0;i<ids.length;i++) h=((h<<5)+h)+ids.charCodeAt(i); return String(h>>>0);})();
  (function loadSaved(){
    try {
      const saved = localStorage.getItem(LAYOUT_KEY);
      if(saved){
        const mp = new Map(JSON.parse(saved).map(p => [p.id, p]));
        DATA.nodes.forEach(n => { const p = mp.get(n.id); if(p){ n.x=p.x; n.y=p.y; n.fixed=true; }});
      } else { ringsLayout(); }
    } catch(_) { ringsLayout(); }
  })();

  // ---------- Node size ----------
  let sizeBy = (localStorage.getItem("pcSizeBy") || "auto");
  let sizeScale = Number(localStorage.getItem("pcSizeScale") || "1") || 1;
  sizeBySel.value = sizeBy;
  sizeScaleEl.value = String(sizeScale);
  sizeScaleVal.textContent = sizeScale.toFixed(1);

  let hullStyle = localStorage.getItem("pcHullStyle") || "smooth";
  hullStyleSel.value = hullStyle;

  let includeRefs = (localStorage.getItem("pcIncludeRefs") || "0") === "1";
  chkRefs.checked = includeRefs;

  let edgeMode = localStorage.getItem("pcEdgeMode") || "auto";
  edgeModeSel.value = edgeMode;

  let minW = Number(localStorage.getItem("pcMinW") || "1") || 1;
  minWEl.value = String(minW);
  minWVal.textContent = String(minW);

  let onlyDoi = (localStorage.getItem("pcOnlyDoi") || "0") === "1";
  onlyDoiEl.checked = onlyDoi;

  let hideIso = (localStorage.getItem("pcHideIso") || "1") === "1";
  hideIsoEl.checked = hideIso;

  let highlightGaps = (localStorage.getItem("pcHighlightGaps") || "0") === "1";
  if (chkGaps) chkGaps.checked = highlightGaps;

  let edgeOpacity = Number(localStorage.getItem("pcEdgeOpacity") || "0.5") || 0.5;
  if (edgeOpacityEl) { edgeOpacityEl.value = String(edgeOpacity); edgeOpacityVal.textContent = edgeOpacity.toFixed(2); }

  function metricValue(n, metric){
    if (metric === "pagerank") return (typeof n.pagerank === "number" && !Number.isNaN(n.pagerank)) ? n.pagerank : 0;
    if (metric === "degree")   return n.degree || 0;
    return 1;
  }
  function chosenMetric(){
    if (sizeBy === "auto"){
      const hasPR = DATA.nodes.some(n => typeof n.pagerank === "number" && !Number.isNaN(n.pagerank));
      return hasPR ? "pagerank" : "degree";
    }
    return sizeBy;
  }
  function metricRange(metric){
    let min = +Infinity, max = -Infinity;
    for (const n of DATA.nodes){
      if (!includeRefs && n.external) continue;
      const topicMode = (edgeMode === "topic_membership" || edgeMode === "topic_relations");
      if (!topicMode && onlyDoi && !(n.doi || n.has_doi)) continue;
      const v = metricValue(n, metric);
      if (v < min) min = v;
      if (v > max) max = v;
    }
    if (!isFinite(min) || !isFinite(max)) { min = 0; max = 1; }
    if (min === max) { max = min + 1; }
    return {min, max};
  }
  let _rangeCache = metricRange(chosenMetric());
  function nodeRadius(n){
    const metric = chosenMetric();
    if (metric === "constant") return 9 * sizeScale * (n.external ? 0.85 : 1);
    const r = _rangeCache;
    const v = metricValue(n, metric);
    const t = Math.sqrt(Math.max(0, Math.min(1, (v - r.min) / (r.max - r.min))));
    const minR = 6, maxR = 24;
    return (minR + (maxR - minR) * t) * sizeScale * (n.external ? 0.9 : 1);
  }

  // ---------- Edge mode & filtering ----------
  function computeEdgesForMode(mode){
    const base = EDGESETS[mode] || [];
    const out = [];
    const topicMode = (mode === "topic_membership" || mode === "topic_relations");
    for (const e of base){
      const s = byId.get(e.source), t = byId.get(e.target);
      if (!s || !t) continue;
      if (!includeRefs && ((s.external) || (t.external))) continue;
      if (!topicMode && onlyDoi && (! (s.doi || s.has_doi) || ! (t.doi || t.has_doi))) continue;
      if ((e.weight || 1) < minW) continue;
      out.push(e);
    }
    return out;
  }
  function currentEdges(){ return computeEdgesForMode(edgeMode); }
  function activeNodeSet(edges){
    const S = new Set();
    edges.forEach(e => { S.add(e.source); S.add(e.target); });
    return S;
  }
  function countComponents(edges){
    const adj = new Map();
    edges.forEach(e => {
      const a=e.source, b=e.target;
      (adj.get(a) || adj.set(a, new Set()).get(a)).add(b);
      (adj.get(b) || adj.set(b, new Set()).get(b)).add(a);
    });
    const nodes = [...adj.keys()];
    const seen = new Set();
    let comps = 0;
    for (const n of nodes){
      if (seen.has(n)) continue;
      comps++;
      const q=[n]; seen.add(n);
      while(q.length){
        const x=q.pop();
        (adj.get(x)||[]).forEach(y => { if(!seen.has(y)){ seen.add(y); q.push(y);} });
      }
    }
    if (edges.length === 0){
      let cnt=0;
      DATA.nodes.forEach(n => { if (shouldDisplay(n, null)) cnt++; });
      return Math.max(comps, cnt);
    }
    return comps;
  }
  function chooseBestEdgeMode(){
    const candidates = ["citations","shared_refs","semantic","suggested"].filter(m => EDGESETS[m] && EDGESETS[m].length);
    if (!candidates.length) return edgeMode;
    let best = candidates[0], bestScore = [+Infinity, 0]; // [components, -edges]
    for (const m of candidates){
      const E = computeEdgesForMode(m);
      const comps = countComponents(E);
      const score = [comps, -E.length];
      if (score[0] < bestScore[0] || (score[0] === bestScore[0] && score[1] < bestScore[1])){
        best = m; bestScore = score;
      }
    }
    return best;
  }

  // ---------- Draw ----------
  function drawEdges(){
    const E = currentEdges();
    edgesG.innerHTML = E.map(e => {
      const s = byId.get(e.source), t = byId.get(e.target);
      const sw = Math.max(1, Math.min(6, 1 + Math.log2(1 + (e.weight||1))));
      return `<line class="edge" data-s="${s.id}" data-t="${t.id}" x1="${s.x}" y1="${s.y}" x2="${t.x}" y2="${t.y}" stroke-width="${sw}" stroke-opacity="${edgeOpacity}"></line>`;
    }).join("");
    document.getElementById('nEdges').textContent = E.length;
    nCompEl.textContent = countComponents(E);
  }

  function drawNodes(){
    nodesG.innerHTML = DATA.nodes.map(n => {
      const c = COLORS[n.cluster % COLORS.length];
      const name = n.topic ? (n.title || `Topic ${n.cluster}`) : n.title;
      const short = (name.length > 36) ? (name.slice(0, 33) + "…") : name;
      const tt = [ name, n.year ? ("Year: " + n.year) : "", n.terms && n.terms.length ? ("Terms: " + n.terms.slice(0,6).join(", ")) : "" ].filter(Boolean).join("\n");
      const r = nodeRadius(n);

      if (n.topic){
        const w = r * 2.6, h = r * 1.6;
        return `<g class="node ${n.external?'external':''}" data-id="${n.id}" transform="translate(${n.x},${n.y})">
          <rect x="${-w/2}" y="${-h/2}" width="${w}" height="${h}" rx="8" ry="8" fill="${c}" style="stroke-dasharray:0;opacity:.95"></rect>
          <title>${tt}</title>
          <text y="${h/2 + 12}" text-anchor="middle">${short}</text>
        </g>`;
      }

      return `<g class="node ${n.external?'external':''}" data-id="${n.id}" transform="translate(${n.x},${n.y})">
        <circle r="${r}" fill="${c}" ${n.external?'style="stroke-dasharray:4 3;opacity:.92"':''}></circle>
        <title>${tt}</title>
        <text y="${r+12}" text-anchor="middle">${short}</text>
      </g>`;
    }).join("");
    applyNodeVisibility();
  }

  function updateEdgesForNode(id){
    document.querySelectorAll(`line.edge[data-s="${id}"], line.edge[data-t="${id}"]`).forEach(l => {
      const s = byId.get(l.dataset.s), t = byId.get(l.dataset.t);
      l.setAttribute('x1', s.x); l.setAttribute('y1', s.y);
      l.setAttribute('x2', t.x); l.setAttribute('y2', t.y);
    });
  }

  function shouldDisplay(n, activeSet){
    if (!includeRefs && n.external) return false;
    const topicMode = (edgeMode === "topic_membership" || edgeMode === "topic_relations");
    if (!topicMode && onlyDoi && !(n.doi || n.has_doi)) return false;
    if (hideIso && activeSet && !activeSet.has(n.id)) return false;
    return true;
  }

  function applyNodeVisibility(){
    const E = currentEdges();
    const active = activeNodeSet(E);
    document.querySelectorAll('g.node').forEach(g => {
      const n = byId.get(g.dataset.id);
      g.style.display = shouldDisplay(n, active) ? "" : "none";
    });
  }

  function updateAllPositions(){
    document.querySelectorAll('g.node').forEach(g => {
      const n = byId.get(g.dataset.id);
      g.setAttribute('transform', `translate(${n.x},${n.y})`);
      const r = nodeRadius(n);
      const text = g.querySelector('text');
      if (n.topic){
        const w = r * 2.6, h = r * 1.6;
        const rect = g.querySelector('rect');
        if (rect){ rect.setAttribute('x', String(-w/2)); rect.setAttribute('y', String(-h/2)); rect.setAttribute('width', String(w)); rect.setAttribute('height', String(h)); }
        if (text) text.setAttribute('y', String(h/2 + 12));
      } else {
        if (text) text.setAttribute('y', String(r + 12));
      }
    });
    document.querySelectorAll('line.edge').forEach(l => {
      const s = byId.get(l.dataset.s), t = byId.get(l.dataset.t);
      l.setAttribute('x1', s.x); l.setAttribute('y1', s.y);
      l.setAttribute('x2', t.x); l.setAttribute('y2', t.y);
    });
    updateHulls();
  }

  // ---------- Hulls ----------
  let showHulls = true, showLabels = true;

  function groupsByCluster(){
    const g = new Map();
    DATA.nodes.forEach(n => {
      if (n.external) return;
      const el = nodesG.querySelector(`g.node[data-id="${CSS.escape(n.id)}"]`);
      if (!el || el.style.display === 'none') return;
      (g.get(n.cluster) || g.set(n.cluster, []).get(n.cluster)).push(n);
    });
    return g;
  }

  function convexHull(pts){
    if (pts.length <= 1) return pts.slice();
    const P = pts.slice().sort((a,b)=>a.x===b.x ? a.y-b.y : a.x-b.x);
    const cross = (o,a,b)=> (a.x-o.x)*(b.y-o.y)-(a.y-o.y)*(b.x-o.x);
    const lower=[]; for(const p of P){ while(lower.length>=2 && cross(lower[lower.length-2], lower[lower.length-1], p) <= 0) lower.pop(); lower.push(p); }
    const upper=[]; for(let i=P.length-1;i>=0;i--){ const p=P[i]; while(upper.length>=2 && cross(upper[upper.length-2], upper[upper.length-1], p) <= 0) upper.pop(); upper.push(p); }
    upper.pop(); lower.pop();
    return lower.concat(upper);
  }

  function chaikin(points, iters){
    let pts = points.slice();
    for (let k=0; k<iters; k++){
      const out=[];
      for (let i=0; i<pts.length; i++){
        const p = pts[i], q = pts[(i+1)%pts.length];
        out.push({x: 0.75*p.x + 0.25*q.x, y: 0.75*p.y + 0.25*q.y});
        out.push({x: 0.25*p.x + 0.75*q.x, y: 0.25*p.y + 0.75*q.y});
      }
      pts = out;
    }
    return pts;
  }

  function hullPath(points, pad){
    if (!points.length) return "";
    let cx=0, cy=0; points.forEach(p => { cx+=p.x; cy+=p.y; }); cx/=points.length; cy/=points.length;
    const inflated = points.map(p => {
      const vx = p.x - cx, vy = p.y - cy;
      const len = Math.hypot(vx,vy) || 1;
      return {x: p.x + (vx/len)*pad, y: p.y + (vy/len)*pad};
    });
    const hull = convexHull(inflated);
    const smooth = chaikin(hull, 2);
    return "M " + smooth.map(p => `${p.x} ${p.y}`).join(" L ") + " Z";
  }

  function updateHulls(){
    const style = hullStyle;
    if (!showHulls || style === "none"){ hullsG.innerHTML = ""; labelsG.innerHTML = showLabels ? labelsOnly() : ""; return; }

    const H=[], L=[];
    for (const [cid, nodes] of groupsByCluster()){
      if (!nodes.length) continue;
      const color = COLORS[cid % COLORS.length];

      let sx=0, sy=0; nodes.forEach(n=>{sx+=n.x; sy+=n.y;}); const cx=sx/nodes.length, cy=sy/nodes.length;
      const topic = (DATA.topics||[]).find(t => t.cluster===cid);
      const words = clusterLabel(topic) || `Cluster ${cid}`;

      if (style === "circle"){
        let r = 0; nodes.forEach(n => { const dx=n.x-cx, dy=n.y-cy; r = Math.max(r, Math.hypot(dx,dy) + nodeRadius(n)); });
        r += 18; // smaller pad than before
        H.push(`<circle class="hull" data-cluster="${cid}" cx="${cx}" cy="${cy}" r="${r}" stroke="${color}aa" fill="${color}22"></circle>`);
      } else {
        const pts = nodes.map(n => ({x:n.x, y:n.y}));
        const pad = 14 + Math.max(...nodes.map(n => nodeRadius(n)), 8);
        const d = (style === "smooth") ? hullPath(pts, pad) : (function(){
          let cx2=0, cy2=0; pts.forEach(p=>{cx2+=p.x; cy2+=p.y;}); cx2/=pts.length; cy2/=pts.length;
          const inflated = pts.map(p => {
            const vx = p.x - cx2, vy = p.y - cy2; const len=Math.hypot(vx,vy)||1;
            return {x:p.x+(vx/len)*pad, y:p.y+(vy/len)*pad};
          });
          const hull = convexHull(inflated);
          return "M " + hull.map(p => `${p.x} ${p.y}`).join(" L ") + " Z";
        })();
        H.push(`<path class="hull" data-cluster="${cid}" d="${d}" stroke="${color}aa" fill="${color}22"></path>`);
      }
      if (showLabels){
        L.push(`<text class="cluster-label" x="${cx}" y="${cy}">${words}</text>`);
      }
    }
    hullsG.innerHTML = H.join(""); labelsG.innerHTML = showLabels ? L.join("") : "";
  }

  function labelsOnly(){
    const out=[];
    for(const [cid, nodes] of groupsByCluster()){
      if(!nodes.length) continue;
      let sx=0, sy=0; nodes.forEach(n=>{sx+=n.x; sy+=n.y;}); const cx=sx/nodes.length, cy=sy/nodes.length;
      const t=(DATA.topics||[]).find(t=>t.cluster===cid);
      const words = clusterLabel(t) || `Cluster ${cid}`;
      out.push(`<text class="cluster-label" x="${cx}" y="${cy}">${words}</text>`);
    }
    return out.join("");
  }

  // First render
  if (edgeMode === "auto") {
    edgeMode = chooseBestEdgeMode();
    edgeModeSel.value = edgeMode;
    localStorage.setItem("pcEdgeMode", edgeMode);
  }
  drawEdges(); drawNodes(); updateHulls();
  applyGapHighlight();

  // ---------- Interactions ----------
  function highlight(id, on){
    document.querySelectorAll('g.node').forEach(g => {
      const hit = (g.dataset.id === id);
      g.classList.toggle('hl', on && hit);
      g.classList.toggle('dim', on && !hit);
    });
    document.querySelectorAll('line.edge').forEach(l => {
      const hit = (l.dataset.s === id || l.dataset.t === id);
      l.classList.toggle('hl', on && hit);
      l.classList.toggle('dim', on && !hit);
    });
  }
  nodesG.addEventListener('mouseover', e => { const g=e.target.closest('g.node'); if(!g) return; highlight(g.dataset.id,true); });
  nodesG.addEventListener('mouseout',  e => { const g=e.target.closest('g.node'); if(!g) return; highlight(g.dataset.id,false); });
  nodesG.addEventListener('click',     e => { const g=e.target.closest('g.node'); if(!g) return; window.open('/captures/'+g.dataset.id+'/', '_blank'); });

  // Hull click → select cluster
  hullsG.addEventListener('click', (e) => {
    const path = e.target.closest('.hull'); if (!path) return;
    const cid = Number(path.getAttribute('data-cluster'));
    selectCluster(cid);
  });

  // Spotlight cluster
  function spotlightCluster(cid){
    document.querySelectorAll('g.node').forEach(g => { const n=byId.get(g.dataset.id); g.classList.toggle('dim', n.cluster!==cid); });
    document.querySelectorAll('line.edge').forEach(l => {
      const keep = byId.get(l.dataset.s).cluster===cid || byId.get(l.dataset.t).cluster===cid;
      l.classList.toggle('dim', !keep);
    });
    document.querySelectorAll('.hull').forEach(h => h.style.opacity = (Number(h.dataset.cluster)===cid) ? "1" : ".15");
  }

  // Search
  document.getElementById('q').addEventListener('input', (e) => {
    const q = e.target.value.trim().toLowerCase();
    if(!q){
      document.querySelectorAll('g.node, line.edge').forEach(el => el.classList.remove('dim'));
      document.querySelectorAll('.hull').forEach(h => h.style.opacity = "1");
      applyGapHighlight();
      return;
    }
    const ok = new Set();
    DATA.nodes.forEach(n => {
      const hay = (n.title + " " + (n.terms||[]).join(" ")).toLowerCase();
      if(hay.includes(q)) ok.add(n.id);
    });
    document.querySelectorAll('g.node').forEach(g => g.classList.toggle('dim', !ok.has(g.dataset.id)));
    document.querySelectorAll('line.edge').forEach(l => {
      const keep = ok.has(l.dataset.s) || ok.has(l.dataset.t);
      l.classList.toggle('dim', !keep);
    });
    const visibleClusters = new Set(DATA.nodes.filter(n => ok.has(n.id) && shouldDisplay(n, null)).map(n => n.cluster));
    document.querySelectorAll('.hull').forEach(h => h.style.opacity = visibleClusters.has(Number(h.dataset.cluster)) ? "1" : ".12");
  });

  // Pan & zoom
  let pan = { k: 1, x: 0, y: 0 };
  function applyPan(){ scene.setAttribute('transform', `translate(${pan.x},${pan.y}) scale(${pan.k})`); }
  applyPan();
  function clientToGraph(clientX, clientY){
    const r = svg.getBoundingClientRect();
    const mx = clientX - r.left, my = clientY - r.top;
    return { x: (mx - pan.x) / pan.k, y: (my - pan.y) / pan.k };
    }

  svg.addEventListener('wheel', (e) => {
    e.preventDefault();
    const r = svg.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const zx = (mx - pan.x) / pan.k, zy = (my - pan.y) / pan.k;
    const fac = Math.exp(-e.deltaY * 0.002);
    pan.k = Math.max(0.2, Math.min(8, pan.k * fac));
    pan.x = mx - zx * pan.k; pan.y = my - zy * pan.k;
    applyPan();
  }, { passive:false });

  let panning=false, lastX=0, lastY=0;
  svg.addEventListener('mousedown', (e) => {
    if (e.target.closest('g.node')) return;
    panning = true; lastX = e.clientX; lastY = e.clientY; e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if(!panning) return;
    pan.x += (e.clientX - lastX); pan.y += (e.clientY - lastY);
    lastX = e.clientX; lastY = e.clientY;
    applyPan();
  });
  window.addEventListener('mouseup', () => { panning=false; });
  svg.addEventListener('dblclick', () => { pan = {k:1,x:0,y:0}; applyPan(); });

  // Physics
  let simRunning = false, simAlpha = 0.0, simFrame = null;
  const springK = 0.008, restL = 120, gravity = 0.002;
  const REPULSE = 1800;
  const N = DATA.nodes.length;

  function forceStep(alpha){
    const E = currentEdges();
    const edgeNodes = activeNodeSet(E);
    if (N <= 400){
      const arr = DATA.nodes.filter(n => edgeNodes.has(n.id));
      for (let i=0;i<arr.length;i++){
        const a = arr[i]; if (a.fixed) continue;
        for (let j=i+1;j<arr.length;j++){
          const b = arr[j]; if (b.fixed) continue;
          let dx=a.x-b.x, dy=a.y-b.y;
          let d2=dx*dx + dy*dy + 0.01;
          let d=Math.sqrt(d2);
          let f = REPULSE / d2;
          let fx = (dx/d)*f, fy=(dy/d)*f;
          a.vx=(a.vx||0)+fx; a.vy=(a.vy||0)+fy;
          b.vx=(b.vx||0)-fx; b.vy=(b.vy||0)-fy;
        }
      }
    }
    for (const l of edgesG.querySelectorAll('line.edge')){
      const s = byId.get(l.dataset.s), t = byId.get(l.dataset.t);
      let dx=t.x-s.x, dy=t.y-s.y, d=Math.sqrt(dx*dx+dy*dy)+0.01;
      const sw = Number(l.getAttribute('stroke-width') || 1);
      let force = (d-restL) * springK * Math.max(1, Math.min(4, sw));
      let fx=(dx/d)*force, fy=(dy/d)*force;
      if(!s.fixed){ s.vx=(s.vx||0)+fx; s.vy=(s.vy||0)+fy; }
      if(!t.fixed){ t.vx=(t.vx||0)-fx; t.vy=(t.vy||0)-fy; }
    }
    const cent = new Map();
    DATA.nodes.forEach(n => {
      const el = nodesG.querySelector(`g.node[data-id="${CSS.escape(n.id)}"]`);
      if (!el || el.style.display === 'none') return;
      let c = cent.get(n.cluster) || (cent.set(n.cluster,{x:0,y:0,cnt:0}), cent.get(n.cluster));
      c.x+=n.x; c.y+=n.y; c.cnt++;
    });
    cent.forEach(v=>{ v.x/=v.cnt; v.y/=v.cnt; });
    DATA.nodes.forEach(n => {
      if(n.fixed) return;
      const el = nodesG.querySelector(`g.node[data-id="${CSS.escape(n.id)}"]`);
      if (!el || el.style.display === 'none') return;
      const c=cent.get(n.cluster); if(!c) return;
      n.vx=(n.vx||0)+ (c.x-n.x)*gravity; n.vy=(n.vy||0)+ (c.y-n.y)*gravity;
    });
    DATA.nodes.forEach(n => {
      if(n.fixed){ n.vx=0; n.vy=0; return; }
      n.vx *= 0.86; n.vy *= 0.86;
      n.x += (n.vx||0) * alpha;
      n.y += (n.vy||0) * alpha;
    });
  }

  function startSim(alpha=0.25){
    if (simRunning) { simAlpha = Math.max(simAlpha, alpha); return; }
    simRunning = true; simAlpha = alpha;
    const loop = () => {
      if (!simRunning) return;
      const a = Math.max(0.02, simAlpha);
      forceStep(a);
      updateAllPositions();
      simAlpha *= 0.985;
      if (simAlpha < 0.02 && !dragging) { simRunning = false; simFrame=null; return; }
      simFrame = requestAnimationFrame(loop);
    };
    simFrame = requestAnimationFrame(loop);
  }
  function nudge(){ startSim(0.18); }

  // Dragging
  let dragging = null;
  nodesG.addEventListener('pointerdown', (e) => {
    const g = e.target.closest('g.node'); if(!g) return;
    e.stopPropagation();
    const n = byId.get(g.dataset.id);
    const pt = clientToGraph(e.clientX, e.clientY);
    dragging = { n, g, dx: n.x - pt.x, dy: n.y - pt.y };
    n.fixed = true;
    g.classList.add('dragging');
    nodesG.setPointerCapture(e.pointerId);
    startSim(0.25);
  });
  nodesG.addEventListener('pointermove', (e) => {
    if(!dragging) return;
    const {n, g, dx, dy} = dragging;
    const pt = clientToGraph(e.clientX, e.clientY);
    n.x = pt.x + dx; n.y = pt.y + dy;
    g.setAttribute('transform', `translate(${n.x},${n.y})`);
    updateEdgesForNode(n.id);
    updateHulls();
  });
  window.addEventListener('pointerup', () => {
    if(!dragging) return;
    dragging.g.classList.remove('dragging');
    dragging = null;
    startSim(0.18);
  });

  // Gap highlight
  function applyGapHighlight(){
    if (!highlightGaps){
      document.querySelectorAll('g.node, line.edge').forEach(el => el.classList.remove('dim'));
      return;
    }
    document.querySelectorAll('g.node').forEach(g => {
      const n = byId.get(g.dataset.id);
      g.classList.toggle('dim', !n?.gap);
    });
    document.querySelectorAll('line.edge').forEach(l => {
      const s = byId.get(l.dataset.s), t = byId.get(l.dataset.t);
      const keep = (s?.gap && t?.gap);
      l.classList.toggle('dim', !keep);
    });
  }

  // Controls
  function redrawAll(){ drawEdges(); applyNodeVisibility(); updateAllPositions(); applyGapHighlight(); nudge(); }

  document.getElementById('btnRings').addEventListener('click', () => { ringsLayout(); updateAllPositions(); nudge(); });
  document.getElementById('btnForce').addEventListener('click', () => { startSim(0.35); });
  btnConnect.addEventListener('click', () => {
    edgeMode = chooseBestEdgeMode();
    edgeModeSel.value = edgeMode;
    localStorage.setItem("pcEdgeMode", edgeMode);
    redrawAll();
  });
  document.getElementById('btnSave').addEventListener('click', () => {
    const pos = DATA.nodes.map(n => ({id:n.id, x:n.x, y:n.y}));
    try { localStorage.setItem("pc-layout-" + "save", JSON.stringify(pos)); alert("Layout saved."); } catch(e){ console.warn(e); }
  });
  document.getElementById('btnReset').addEventListener('click', () => { pan = {k:1,x:0,y:0}; applyPan(); });
  document.getElementById('btnUnfix').addEventListener('click', () => { DATA.nodes.forEach(n => n.fixed = false); nudge(); });

  document.getElementById('chkHulls').addEventListener('change', (e) => { showHulls = e.target.checked; updateHulls(); });
  document.getElementById('chkLabels').addEventListener('change', (e) => { showLabels = e.target.checked; updateHulls(); });

  hullStyleSel.addEventListener('change', () => {
    hullStyle = hullStyleSel.value; localStorage.setItem("pcHullStyle", hullStyle);
    updateHulls();
  });

  chkRefs.addEventListener('change', () => {
    includeRefs = chkRefs.checked; localStorage.setItem("pcIncludeRefs", includeRefs ? "1" : "0");
    _rangeCache = metricRange(chosenMetric());
    redrawAll();
  });

  edgeModeSel.addEventListener('change', () => {
    const sel = edgeModeSel.value;
    if (sel === "auto"){
      edgeMode = chooseBestEdgeMode();
      edgeModeSel.value = edgeMode;
    } else {
      edgeMode = sel;
    }
    localStorage.setItem("pcEdgeMode", edgeMode);
    redrawAll();
  });

  minWEl.addEventListener('input', () => {
    minW = Number(minWEl.value) || 1; minWVal.textContent = String(minW);
    localStorage.setItem("pcMinW", String(minW));
    redrawAll();
  });
  onlyDoiEl.addEventListener('change', () => {
    onlyDoi = onlyDoiEl.checked; localStorage.setItem("pcOnlyDoi", onlyDoi ? "1" : "0");
    _rangeCache = metricRange(chosenMetric());
    redrawAll();
  });
  hideIsoEl.addEventListener('change', () => {
    hideIso = hideIsoEl.checked; localStorage.setItem("pcHideIso", hideIso ? "1" : "0");
    redrawAll();
  });

  sizeBySel.addEventListener('change', () => {
    sizeBy = sizeBySel.value; localStorage.setItem("pcSizeBy", sizeBy);
    _rangeCache = metricRange(chosenMetric());
    drawNodes(); updateAllPositions(); applyGapHighlight();
  });
  sizeScaleEl.addEventListener('input', () => {
    sizeScale = Number(sizeScaleEl.value) || 1; localStorage.setItem("pcSizeScale", String(sizeScale));
    sizeScaleVal.textContent = sizeScale.toFixed(1);
    drawNodes(); updateAllPositions(); applyGapHighlight();
  });

  if (chkGaps){
    chkGaps.addEventListener('change', () => {
      highlightGaps = chkGaps.checked;
      localStorage.setItem("pcHighlightGaps", highlightGaps ? "1" : "0");
      applyGapHighlight();
    });
  }

  if (edgeOpacityEl){
    edgeOpacityEl.addEventListener('input', () => {
      edgeOpacity = Number(edgeOpacityEl.value) || 0.5;
      edgeOpacityVal.textContent = edgeOpacity.toFixed(2);
      localStorage.setItem("pcEdgeOpacity", String(edgeOpacity));
      drawEdges();
    });
  }
})();
