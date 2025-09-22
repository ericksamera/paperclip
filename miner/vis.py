from __future__ import annotations
from pathlib import Path
import json

_HTML = """<!doctype html>
<meta charset="utf-8"/>
<title>Paperclip Graph — Themes (Dynamic)</title>
<style>
  :root {
    --bar-h: 62px;
    --panel-w: 340px;
    --gap: 10px;
    --bg: #ffffff;
    --ink: #111;
    --muted: #666;
    --line: #e6e6e6;
  }
  * { box-sizing: border-box; }
  html, body { margin:0; height:100%; background:var(--bg); color:var(--ink); font: 13px/1.45 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
  #top {
    height: var(--bar-h);
    display:flex; align-items:center; gap:10px; padding:8px 12px; border-bottom:1px solid var(--line);
    position:relative;
  }
  .badge { display:inline-flex; align-items:center; gap:6px; padding:3px 8px; border:1px solid #cfcfcf; border-radius:999px; background:#fafafa; font-size:12px; }
  #q { width: 340px; padding:8px 10px; border:1px solid var(--line); border-radius:8px; outline:none; }
  #wrap { position:relative; height: calc(100vh - var(--bar-h)); width:100vw; overflow:hidden; }
  #leftpanel {
    position:absolute; top:10px; left:10px; width: var(--panel-w);
    max-height: calc(100% - 20px); overflow:auto; padding:10px; background:#fff;
    border:1px solid var(--line); border-radius:10px; box-shadow: 0 8px 24px rgba(0,0,0,0.06);
  }
  .section { margin-bottom:14px; }
  .section h3 { margin:0 0 8px 0; font-size:12px; font-weight:700; letter-spacing: .02em; color:#222; text-transform:uppercase; }
  .row { display:flex; align-items:center; gap:8px; padding:6px 4px; border-radius:6px; cursor:pointer; }
  .row:hover { background:#f6f6f6; }
  .row.disabled { opacity:.35 }
  .swatch { width:14px; height:14px; border-radius:3px; border:1px solid rgba(0,0,0,0.15); flex:0 0 auto; }
  .label { font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .pct { margin-left:auto; font-variant-numeric: tabular-nums; color:#444; font-size:12px; }
  .slider { width:100%; }
  .control { display:flex; align-items:center; gap:8px; margin:6px 0; }
  .control label { width:130px; color:#333; font-size:12px; }
  .muted { color: var(--muted); }
  #canvas { position:absolute; left:0; top:0; width:100%; height:100%; display:block; }
  #tip {
    position:absolute; display:none; padding:6px 8px; font-size:12px; background:#fff;
    border:1px solid #ddd; border-radius:6px; box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    pointer-events:none; max-width:320px;
  }
  #minimap {
    position:absolute; right:10px; bottom:10px; width: 200px; height:140px; background:#fff;
    border:1px solid var(--line); border-radius:8px; box-shadow: 0 6px 18px rgba(0,0,0,0.06);
  }
  #buttons { display:flex; gap:6px; flex-wrap:wrap; }
  button {
    appearance:none; border:1px solid #ccc; background:#fff; padding:6px 8px; border-radius:8px; cursor:pointer; font-size:12px;
  }
  button:active { transform: translateY(1px); }
  .pill { padding:2px 6px; border-radius:999px; border:1px solid #bbb; }
</style>

<div id="top">
  <span class="badge" id="count">0 nodes</span>
  <span class="badge" id="edges">0 edges</span>
  <input id="q" type="search" placeholder="Search title / citekey / DOI / URL (Regex ok: /pattern/)" />
  <span class="badge"><input id="anim" type="checkbox" checked /> <label for="anim">Animate</label></span>
  <span class="badge"><input id="pinDrag" type="checkbox" checked /> <label for="pinDrag">Pin on drag</label></span>
  <span class="badge"><input id="fadeMode" type="checkbox" checked /> <label for="fadeMode">Fade hidden</label></span>
  <span class="badge">Depth <input id="depth" type="range" min="0" max="3" step="1" value="0" style="vertical-align:middle"> <span id="depthVal" class="pill">0</span></span>
</div>

<div id="wrap">
  <div id="leftpanel">
    <div class="section" id="legendSec">
      <h3>Themes</h3>
      <div id="legend"></div>
      <div class="muted" style="margin-top:6px;">Click to toggle • Shift+Click to isolate</div>
    </div>

    <div class="section" id="physicsSec">
      <h3>Physics</h3>
      <div class="control"><label>Repulsion</label><input id="repel" class="slider" type="range" min="100" max="2500" value="1200"><span id="repelVal" class="muted">1200</span></div>
      <div class="control"><label>Spring</label><input id="spring" class="slider" type="range" min="1" max="50" value="10"><span id="springVal" class="muted">0.010</span></div>
      <div class="control"><label>Damping</label><input id="damp" class="slider" type="range" min="70" max="95" value="85"><span id="dampVal" class="muted">0.85</span></div>
      <div class="control"><label>Center pull</label><input id="center" class="slider" type="range" min="0" max="30" value="5"><span id="centerVal" class="muted">0.005</span></div>
      <div id="buttons" style="margin-top:8px;">
        <button id="resetLayout">Reset layout</button>
        <button id="centerView">Center view</button>
        <button id="savePos">Save</button>
        <button id="loadPos">Load</button>
        <button id="clearPos">Clear</button>
        <button id="exportPng">Export PNG</button>
      </div>
    </div>

    <div class="section">
      <h3>View</h3>
      <div class="control"><label><input id="labels" type="checkbox" checked> Labels on hover/selection</label></div>
    </div>
  </div>

  <canvas id="canvas"></canvas>
  <canvas id="minimap"></canvas>
  <div id="tip"></div>
</div>

<script>
// ====== Inline data (no fetch) ======
const G = __GRAPH_JSON__;
const THEMES = __THEMES_JSON__ || {};
const nodes = G.nodes || [];
const edges = G.edges || [];
const N = nodes.length;

// ====== Counters ======
document.getElementById('count').textContent = N + ' nodes';
document.getElementById('edges').textContent = edges.length + ' edges';

// ====== Utilities ======
function colorForCluster(c){
  const h = ((parseInt(c,10)+1) * 137.508) % 360;
  return `hsl(${h},70%,50%)`;
}
function hsla(c,a){ return c.replace('hsl','hsla').replace(')',`,`+a+`)`); }
function clamp(v, lo, hi){ return Math.max(lo, Math.min(hi, v)); }
function lerp(a,b,t){ return a+(b-a)*t; }
function fnv1a(str){ let h=0x811c9dc5; for(let i=0;i<str.length;i++){h^=str.charCodeAt(i);h=(h>>>0)*0x01000193} return (h>>>0).toString(16); }

// ====== Theme metadata & legend ======
const clusterIds = Array.from(new Set(nodes.map(n => n.clusterId))).sort((a,b)=>a-b);
const themeMeta = {};
const totals = { all: N };
for(const cid of clusterIds){
  const meta = THEMES?.[cid] || THEMES?.[String(cid)] || {};
  const size = (meta.size != null) ? meta.size : nodes.filter(n => n.clusterId===cid).length;
  themeMeta[cid] = {
    label: meta.label || `Theme ${cid}`,
    top_terms: meta.top_terms || [],
    size,
    color: colorForCluster(cid)
  };
}
const legend = document.getElementById('legend');
const sortedC = clusterIds.slice().sort((a,b)=>(themeMeta[b].size - themeMeta[a].size));
let activeThemes = new Set(sortedC);
function rebuildLegend(){
  legend.innerHTML = '';
  for(const cid of sortedC){
    const meta = themeMeta[cid];
    const row = document.createElement('div');
    row.className = 'row';
    row.dataset.cid = String(cid);
    row.innerHTML = `
      <div class="swatch" style="background:${meta.color}"></div>
      <div class="label" title="${meta.top_terms.slice(0,8).join(', ')}">${meta.label}</div>
      <div class="pct">${meta.size} • ${((meta.size/N)*100).toFixed(1)}%</div>
    `;
    const setState = ()=>{ row.classList.toggle('disabled', !activeThemes.has(cid)); };
    setState();
    row.addEventListener('click', (e)=>{
      if(e.shiftKey){ activeThemes = new Set([cid]); }
      else { activeThemes.has(cid) ? activeThemes.delete(cid) : activeThemes.add(cid); }
      for(const r of legend.querySelectorAll('.row')) r.classList.toggle('disabled', !activeThemes.has(parseInt(r.dataset.cid)));
      computeVisibility(); // recompute visible sets
    });
    legend.appendChild(row);
  }
}
rebuildLegend();

// ====== Build adjacency ======
const adj = Array.from({length:N}, ()=>[]);
edges.forEach(e => { adj[e.source].push(e.target); adj[e.target].push(e.source); });

// ====== Positions / physics ======
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d', { alpha: false });
const dpr = window.devicePixelRatio || 1;
function resize(){
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width*dpr; canvas.height = rect.height*dpr;
  ctx.setTransform(dpr,0,0,dpr,0,0);
}
function fitCanvas(){ const wrap = document.getElementById('wrap'); canvas.style.width='100%'; canvas.style.height='100%'; resize(); }
window.addEventListener('resize', resize);

let pos = Array.from({length:N}, _=>({x:Math.random()*800-400, y:Math.random()*600-300}));
let vel = Array.from({length:N}, _=>({x:0,y:0}));
let pinned = new Array(N).fill(false);

// Layout persistence
const datasetKey = fnv1a(JSON.stringify(nodes.map(n=>n.docId||n.title||n.id)) + '|' + N);
const LS_KEY = 'pc_graph_pos_' + datasetKey;
function savePositions(){ localStorage.setItem(LS_KEY, JSON.stringify({pos, pinned})); }
function loadPositions(){
  try{
    const s = localStorage.getItem(LS_KEY);
    if(!s) return false;
    const obj = JSON.parse(s);
    if(!obj || !Array.isArray(obj.pos) || obj.pos.length!==N) return false;
    pos = obj.pos; pinned = Array.isArray(obj.pinned) && obj.pinned.length===N ? obj.pinned : new Array(N).fill(false);
    return true;
  }catch(e){ return false; }
}

// Physics params (UI-backed)
const ui = {
  anim: document.getElementById('anim'),
  pinDrag: document.getElementById('pinDrag'),
  fadeMode: document.getElementById('fadeMode'),
  labels: document.getElementById('labels'),
  repel: document.getElementById('repel'),
  spring: document.getElementById('spring'),
  damp: document.getElementById('damp'),
  center: document.getElementById('center'),
  depth: document.getElementById('depth'),
  depthVal: document.getElementById('depthVal'),
  repelVal: document.getElementById('repelVal'),
  springVal: document.getElementById('springVal'),
  dampVal: document.getElementById('dampVal'),
  centerVal: document.getElementById('centerVal'),
  q: document.getElementById('q'),
  exportPng: document.getElementById('exportPng'),
  resetLayout: document.getElementById('resetLayout'),
  centerView: document.getElementById('centerView'),
  savePos: document.getElementById('savePos'),
  loadPos: document.getElementById('loadPos'),
  clearPos: document.getElementById('clearPos'),
};
function syncLabels(){
  ui.repelVal.textContent = parseInt(ui.repel.value);
  ui.springVal.textContent = (parseInt(ui.spring.value)/1000).toFixed(3);
  ui.dampVal.textContent = (parseInt(ui.damp.value)/100).toFixed(2);
  ui.centerVal.textContent = (parseInt(ui.center.value)/1000).toFixed(3);
  ui.depthVal.textContent = ui.depth.value;
}
['input','change'].forEach(ev=>{
  ui.repel.addEventListener(ev, syncLabels);
  ui.spring.addEventListener(ev, syncLabels);
  ui.damp.addEventListener(ev, syncLabels);
  ui.center.addEventListener(ev, syncLabels);
  ui.depth.addEventListener(ev, ()=>{ syncLabels(); computeVisibility(); });
});
syncLabels();

// Pan/zoom
let scale = 1, dx = 0, dy = 0;
function worldToScreen(p){ return {x: p.x*scale + dx, y: p.y*scale + dy}; }
function screenToWorld(x,y){ return {x: (x - dx)/scale, y: (y - dy)/scale}; }

// Drag/select
let dragging=false, dragIdx=-1, lastX=0, lastY=0;
let hover=-1;
let selected = new Set();
canvas.addEventListener('mousedown', e=>{
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX-rect.left), my = (e.clientY-rect.top);
  const w = screenToWorld(mx, my);
  // pick nearest
  let best=-1, bd=1e9;
  for(let i=0;i<N;i++){
    if(!visible[i]) continue;
    const dxp = pos[i].x - w.x, dyp = pos[i].y - w.y;
    const d2 = dxp*dxp + dyp*dyp;
    if(d2<bd){ bd=d2; best=i; }
  }
  if(best>=0 && Math.sqrt(bd) < 16){ dragging=true; dragIdx=best; lastX=mx; lastY=my; if(!e.ctrlKey && !e.metaKey) selected.clear(); selected.add(best); }
  else { dragging=true; dragIdx=-1; lastX=mx; lastY=my; if(!e.ctrlKey && !e.metaKey) selected.clear(); }
});
canvas.addEventListener('mousemove', e=>{
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX-rect.left), my = (e.clientY-rect.top);
  const w = screenToWorld(mx, my);

  // Hover tip
  let best=-1, bd=1e9;
  for(let i=0;i<N;i++){
    if(!visible[i]) continue;
    const dxp = pos[i].x - w.x, dyp = pos[i].y - w.y;
    const d2 = dxp*dxp + dyp*dyp;
    if(d2<bd){ bd=d2; best=i; }
  }
  if(best>=0 && Math.sqrt(bd) < 14){ hover=best; showTip(e.clientX, e.clientY, best); }
  else { hover=-1; hideTip(); }

  if(!dragging) return;
  if(dragIdx>=0){
    const dWorld = screenToWorld(mx,my);
    pos[dragIdx].x = dWorld.x;
    pos[dragIdx].y = dWorld.y;
    if(ui.pinDrag.checked) pinned[dragIdx] = true;
  } else {
    dx += (mx - lastX); dy += (my - lastY);
  }
  lastX = mx; lastY = my;
});
['mouseup','mouseleave'].forEach(ev=>canvas.addEventListener(ev, ()=>{ dragging=false; dragIdx=-1; }));
canvas.addEventListener('dblclick', ()=>{
  // center on selection
  if(!selected.size) return;
  const c = centroid([...selected]);
  centerOn(c.x, c.y);
});

canvas.addEventListener('wheel', e=>{
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX-rect.left), my = (e.clientY-rect.top);
  const before = screenToWorld(mx,my);
  const s = Math.exp(-e.deltaY*0.001);
  scale = clamp(scale*s, 0.2, 6);
  const after = screenToWorld(mx,my);
  dx += (mx - (after.x*scale)) - (mx - (before.x*scale));
  dy += (my - (after.y*scale)) - (my - (before.y*scale));
}, {passive:false});

// Tooltip
const tip = document.getElementById('tip');
function showTip(cx, cy, i){
  const n = nodes[i]; const cid = n.clusterId;
  const meta = themeMeta[cid];
  tip.innerHTML = `<b>${escapeHtml(n.title || n.citekey || n.docId || 'Untitled')}</b><br>
    <span class="muted">${escapeHtml(meta.label)}</span><br>
    <small>${escapeHtml((meta.top_terms||[]).slice(0,8).join(', '))}</small>`;
  tip.style.left = (cx+12)+'px';
  tip.style.top = (cy+8)+'px';
  tip.style.display = 'block';
}
function hideTip(){ tip.style.display = 'none'; }
function escapeHtml(s){ return String(s||'').replace(/[&<>"]/g, m=>({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;'}[m])); }

// ====== Filters: search + themes + local depth ======
let visible = new Array(N).fill(true);
let matchQ = new Array(N).fill(true);
let depthMask = new Array(N).fill(true);

function computeVisibility(){
  // Search filter
  const raw = (ui.q.value || '').trim();
  let asRegex = null;
  if(raw.startsWith('/') && raw.endsWith('/') && raw.length>2){
    try{ asRegex = new RegExp(raw.slice(1,-1), 'i'); } catch(e){ asRegex = null; }
  }
  for(let i=0;i<N;i++){
    const hay = (nodes[i].title||'')+' '+(nodes[i].citekey||'')+' '+(nodes[i].doi||'')+' '+(nodes[i].url||'');
    matchQ[i] = asRegex ? asRegex.test(hay) : hay.toLowerCase().includes(raw.toLowerCase());
  }

  // Local depth (BFS from selected)
  const maxDepth = parseInt(ui.depth.value);
  if(maxDepth>0 && selected.size){
    depthMask.fill(false);
    const q = [...selected].map(i=>({i, d:0}));
    for(const s of q) depthMask[s.i] = true;
    let head=0;
    while(head<q.length){
      const {i,d} = q[head++]; if(d>=maxDepth) continue;
      for(const nb of adj[i]){
        if(!depthMask[nb]){ depthMask[nb]=true; q.push({i:nb, d:d+1}); }
      }
    }
  } else {
    depthMask.fill(true);
  }

  // Theme filter
  for(let i=0;i<N;i++){
    const onTheme = activeThemes.has(nodes[i].clusterId);
    visible[i] = onTheme && matchQ[i] && depthMask[i];
  }

  // Repaint
  needRedraw = true;
}

ui.q.addEventListener('input', computeVisibility);

// ====== Physics engine ======
let needRedraw = true;
function stepPhysics(dt=1){
  const K = parseInt(ui.spring.value)/1000;
  const REP = parseInt(ui.repel.value);
  const DAMP = parseInt(ui.damp.value)/100;
  const CTR = parseInt(ui.center.value)/1000;

  // Simple center pull
  for(let i=0;i<N;i++){
    if(pinned[i]) continue;
    vel[i].x += -pos[i].x * CTR;
    vel[i].y += -pos[i].y * CTR;
  }

  // Springs along edges
  for(const e of edges){
    const i=e.source, j=e.target;
    const dx = pos[j].x - pos[i].x, dy = pos[j].y - pos[i].y;
    vel[i].x += K*dx; vel[i].y += K*dy;
    vel[j].x -= K*dx; vel[j].y -= K*dy;
  }

  // Repulsion (O(n^2); throttle for large N)
  const stride = N>800 ? 2 : 1;
  for(let i=0;i<N;i+=stride){
    for(let j=i+1;j<N;j+=stride){
      const dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y;
      const d2 = Math.max(49, dx*dx + dy*dy);
      const f = REP / d2; const invd = 1/Math.sqrt(d2);
      const fx = f*dx*invd, fy = f*dy*invd;
      if(!pinned[i]){ vel[i].x += fx; vel[i].y += fy; }
      if(!pinned[j]){ vel[j].x -= fx; vel[j].y -= fy; }
    }
  }

  // Integrate + damping
  for(let i=0;i<N;i++){
    if(pinned[i]) continue;
    pos[i].x += vel[i].x*dt; pos[i].y += vel[i].y*dt;
    vel[i].x *= DAMP; vel[i].y *= DAMP;
  }
}

function centroid(list){
  if(!list.length) return {x:0,y:0};
  let x=0,y=0; for(const i of list){ x+=pos[i].x; y+=pos[i].y; } return {x:x/list.length, y:y/list.length};
}
function centerOn(wx, wy){
  const rect = canvas.getBoundingClientRect();
  dx = rect.width/2 - wx*scale;
  dy = rect.height/2 - wy*scale;
  needRedraw = true;
}

// ====== Render ======
function draw(){
    ctx.fillStyle = "#fff";  
    ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Halos per active theme (centroid + spread over visible nodes of that theme)
  for(const cid of sortedC){
    const ids = [];
    for(let i=0;i<N;i++) if(visible[i] && nodes[i].clusterId===cid) ids.push(i);
    if(!ids.length) continue;
    const c = centroid(ids);
    let r2=0; for(const i of ids){ const dx=pos[i].x-c.x, dy=pos[i].y-c.y; r2 += dx*dx+dy*dy; }
    const r = Math.sqrt(r2/ids.length)*1.35 + 22;
    const cs = worldToScreen(c);
    ctx.beginPath(); ctx.arc(cs.x, cs.y, r*scale, 0, Math.PI*2);
    ctx.fillStyle = hsla(themeMeta[cid].color, 0.08); ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = hsla(themeMeta[cid].color, 0.35); ctx.stroke();

    // theme label
    ctx.font = '600 14px system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
    ctx.fillStyle = '#000'; ctx.globalAlpha = 0.85;
    const label = themeMeta[cid].label;
    const tw = ctx.measureText(label).width;
    ctx.fillText(label, cs.x - tw/2, cs.y - r*scale - 6);
    ctx.globalAlpha = 1;
  }

  // Edges
  ctx.lineWidth = 1;
  for(const e of edges){
    const i=e.source, j=e.target;
    const on = visible[i] && visible[j];
    const s = worldToScreen(pos[i]), t = worldToScreen(pos[j]);
    ctx.strokeStyle = on ? 'rgba(0,0,0,0.16)' : (ui.fadeMode.checked ? 'rgba(0,0,0,0.03)' : 'rgba(0,0,0,0)');
    ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y); ctx.stroke();
  }

  // Nodes
  for(let i=0;i<N;i++){
    const on = visible[i];
    const n = nodes[i];
    const c = themeMeta[n.clusterId]?.color || '#444';
    const p = worldToScreen(pos[i]);
    const deg = (n.degree||0);
    const r = 3.5 + Math.sqrt(Math.max(0,deg))*0.6 + (selected.has(i)?2:0);
    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI*2);
    ctx.fillStyle = on ? c : (ui.fadeMode.checked ? 'rgba(0,0,0,0.2)' : 'rgba(0,0,0,0)');
    ctx.fill();
    if(selected.has(i)){
      ctx.lineWidth = 2; ctx.strokeStyle = '#000'; ctx.stroke();
    }
  }

  // Labels (hover/selection)
  if(ui.labels.checked){
    ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
    ctx.fillStyle = '#111';
    const toShow = new Set(selected);
    if(hover>=0) toShow.add(hover);
    for(const i of toShow){
      if(!visible[i]) continue;
      const p = worldToScreen(pos[i]);
      const text = nodes[i].title || nodes[i].citekey || nodes[i].docId || 'Untitled';
      ctx.fillText(text, p.x+8, p.y-8);
    }
  }

  drawMinimap();
}

const mini = document.getElementById('minimap');
const mctx = mini.getContext('2d');
function drawMinimap(){
  const rect = mini.getBoundingClientRect();
  mini.width = rect.width*dpr; mini.height = rect.height*dpr; mctx.setTransform(dpr,0,0,dpr,0,0);
  mctx.clearRect(0,0,mini.width,mini.height);
  // compute world bounds
  let minx=1e9,miny=1e9,maxx=-1e9,maxy=-1e9;
  for(let i=0;i<N;i++){ minx=Math.min(minx,pos[i].x); miny=Math.min(miny,pos[i].y); maxx=Math.max(maxx,pos[i].x); maxy=Math.max(maxy,pos[i].y); }
  const w = maxx-minx, h = maxy-miny;
  const sx = rect.width/(w||1), sy = rect.height/(h||1);
  const s = Math.min(sx, sy)*0.9;
  const ox = (rect.width - w*s)/2 - minx*s, oy = (rect.height - h*s)/2 - miny*s;

  // edges
  mctx.strokeStyle = 'rgba(0,0,0,0.08)'; mctx.lineWidth=1;
  for(const e of edges){
    const i=e.source, j=e.target;
    if(!(visible[i] && visible[j])) continue;
    mctx.beginPath();
    mctx.moveTo(pos[i].x*s+ox, pos[i].y*s+oy);
    mctx.lineTo(pos[j].x*s+ox, pos[j].y*s+oy);
    mctx.stroke();
  }
  // nodes
  for(let i=0;i<N;i++){
    if(!visible[i]) continue;
    mctx.beginPath();
    mctx.arc(pos[i].x*s+ox, pos[i].y*s+oy, 1.8, 0, Math.PI*2);
    mctx.fillStyle = themeMeta[nodes[i].clusterId]?.color || '#444';
    mctx.fill();
  }
  // viewport box
  // map the four corners of screen->world rect back into minimap space
  const rectCanvas = canvas.getBoundingClientRect();
  const tl = screenToWorld(0,0), br = screenToWorld(rectCanvas.width, rectCanvas.height);
  mctx.strokeStyle = 'rgba(0,0,0,0.6)';
  mctx.strokeRect(tl.x*s+ox, tl.y*s+oy, (br.x-tl.x)*s, (br.y-tl.y)*s);
}
mini.addEventListener('click', (e)=>{
  const r = mini.getBoundingClientRect();
  const x = e.clientX - r.left, y = e.clientY - r.top;
  // compute same transform as drawMinimap()
  let minx=1e9,miny=1e9,maxx=-1e9,maxy=-1e9;
  for(let i=0;i<N;i++){ minx=Math.min(minx,pos[i].x); miny=Math.min(miny,pos[i].y); maxx=Math.max(maxx,pos[i].x); maxy=Math.max(maxy,pos[i].y); }
  const w = maxx-minx, h = maxy-miny;
  const sx = r.width/(w||1), sy = r.height/(h||1), s = Math.min(sx,sy)*0.9;
  const ox = (r.width - w*s)/2 - minx*s, oy = (r.height - h*s)/2 - miny*s;

  // convert minimap click to world coords and center there
  const wx = (x - ox)/s, wy = (y - oy)/s;
  centerOn(wx, wy);
});

// ====== Controls ======
ui.resetLayout.addEventListener('click', ()=>{
  pos = Array.from({length:N}, _=>({x:Math.random()*800-400, y:Math.random()*600-300}));
  vel = Array.from({length:N}, _=>({x:0,y:0}));
  pinned = new Array(N).fill(false);
  centerOn(0,0); needRedraw = true;
});
ui.centerView.addEventListener('click', ()=>{
  if(selected.size){ const c = centroid([...selected]); centerOn(c.x, c.y); }
  else centerOn(0,0);
});
ui.savePos.addEventListener('click', savePositions);
ui.loadPos.addEventListener('click', ()=>{ if(loadPositions()) needRedraw=true; });
ui.clearPos.addEventListener('click', ()=>{ localStorage.removeItem(LS_KEY); });
ui.exportPng.addEventListener('click', ()=>{
  const tmp = document.createElement('canvas');
  const r = canvas.getBoundingClientRect();
  tmp.width = r.width*dpr; tmp.height = r.height*dpr;
  const tctx = tmp.getContext('2d'); tctx.setTransform(dpr,0,0,dpr,0,0);
  // white background
  tctx.fillStyle = '#fff'; tctx.fillRect(0,0,tmp.width,tmp.height);
  // draw current frame
  tctx.drawImage(canvas, 0,0);
  const url = tmp.toDataURL('image/png');
  const a = document.createElement('a'); a.href = url; a.download = 'graph.png'; a.click();
});

// ====== Animation loop ======
function frame(){
  if(ui.anim.checked || dragging) {
    stepPhysics(1);
    needRedraw = true;
  }
  if(needRedraw){ draw(); needRedraw=false; }
  requestAnimationFrame(frame);
}

// ====== Init ======
function init(){
  fitCanvas();
  // Try to load saved positions
  if(!loadPositions()){
    // run a few warm-up iterations for nicer start
    for(let i=0;i<260;i++) stepPhysics(1);
  }
  computeVisibility();
  centerOn(0,0);
  frame();
}
init();
</script>
"""

def _escape_for_script(s: str) -> str:
    # Avoid closing the <script> tag from inside JSON (e.g., in titles)
    return s.replace("</", "<\\/").replace("<!--", "<\\!--")

def write_graph_html(graph: dict, themes: dict, out_html: Path):
    """
    Embed both the graph and theme metadata directly into the HTML so it works over file://.
    """
    g = json.dumps(graph, ensure_ascii=False)
    t = json.dumps({int(k): v for k, v in (themes or {}).items()}, ensure_ascii=False)
    html = _HTML.replace("__GRAPH_JSON__", _escape_for_script(g)).replace("__THEMES_JSON__", _escape_for_script(t))
    out_html.write_text(html, encoding="utf-8")
