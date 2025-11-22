// Options panel with Edge set, Physics, and a small color legend.

function injectStyles() {
  if (document.getElementById("pcg-controls-style")) return;
  const css = `
  .pcg-controls{position:absolute;top:10px;right:10px;z-index:10;display:flex;gap:8px;flex-wrap:wrap}
  .pcg-card{background:rgba(255,255,255,.9);color:#111;border-radius:10px;box-shadow:0 6px 20px rgba(0,0,0,.15);padding:10px 12px;font:12px system-ui,Segoe UI,Arial,sans-serif}
  [data-theme="dark"] .pcg-card{background:rgba(25,25,28,.9);color:#eee}
  .pcg-card h4{margin:0 0 6px 0;font-size:12px;font-weight:700;opacity:.85}
  .pcg-row{display:flex;align-items:center;gap:8px;margin:6px 0}
  .pcg-row label{opacity:.8}
  .pcg-select,.pcg-num,.pcg-range{font:12px inherit;padding:3px 6px;border-radius:6px;border:1px solid rgba(0,0,0,.2);background:transparent;color:inherit}
  [data-theme="dark"] .pcg-select,[data-theme="dark"] .pcg-num,[data-theme="dark"] .pcg-range{border-color:rgba(255,255,255,.25)}
  .pcg-btn{font:12px inherit;padding:4px 8px;border-radius:8px;border:1px solid rgba(0,0,0,.2);background:transparent;color:inherit;cursor:pointer}
  .pcg-btn:hover{filter:brightness(1.08)}
  .pcg-btn.primary{background:rgba(99,102,241,.12);border-color:rgba(99,102,241,.35)}
  .pcg-row .pcg-small{opacity:.65}

  /* Legend */
  .pcg-legend{display:grid;grid-template-columns:auto 1fr auto;gap:6px 10px;align-items:center;max-width:280px}
  .pcg-swatch{width:12px;height:12px;border-radius:3px;border:1px solid rgba(0,0,0,.15)}
  [data-theme="dark"] .pcg-swatch{border-color:rgba(255,255,255,.25)}
  .pcg-legend .pcg-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px}
  `;
  const s = document.createElement("style");
  s.id = "pcg-controls-style"; s.textContent = css;
  document.head.appendChild(s);
}

function edgeLabel(key){
  return ({
    doc_citations: "Citations (doc↔doc)",
    citations: "Citations",
    references: "References (doc→ext)",
    semantic: "Semantic (kNN)",
    suggested: "Suggested",
    mutual: "Mutual citations",
    shared_refs: "Shared refs",
    co_cited: "Co-cited",
    topic_relations: "Topic relations",
    topic_membership: "Topic membership",
    edges: "Edges",
  }[key] || key);
}

export function initControls(view) {
  injectStyles();
  const host = document.createElement("div");
  host.className = "pcg-controls";
  view.root.style.position = "relative";
  view.root.appendChild(host);

  // ----- Edge set card -----
  const cardEdges = document.createElement("div");
  cardEdges.className = "pcg-card";
  cardEdges.innerHTML = `
    <h4>Edges</h4>
    <div class="pcg-row">
      <label for="pcg-edge">Set</label>
      <select id="pcg-edge" class="pcg-select"></select>
    </div>
    <div class="pcg-row">
      <label><input id="pcg-hulls" type="checkbox" ${view.showHulls ? "checked" : ""}/> Hulls</label>
    </div>
    <div class="pcg-row">
      <label><input id="pcg-ext" type="checkbox" ${view.includeExternal ? "checked" : ""}/> External refs</label>
    </div>
  `;
  host.appendChild(cardEdges);

  const edgeSel = cardEdges.querySelector("#pcg-edge");
  const hullsCb = cardEdges.querySelector("#pcg-hulls");
  const extCb   = cardEdges.querySelector("#pcg-ext");

  // Populate edge sets
  const sets = view.edgesAvailable();
  for (const k of sets) {
    const opt = document.createElement("option");
    opt.value = k; opt.textContent = edgeLabel(k);
    if (k === view.edgeKey) opt.selected = true;
    edgeSel.appendChild(opt);
  }

  function setExtCheckboxStateFor(key) {
    // Enabled always; defaults vary by set
    if (key === "references") {
      extCb.disabled = false;
      extCb.checked = true;
      view.setIncludeExternal(true);
    } else if (key === "doc_citations" || key === "citations") {
      extCb.disabled = false;
      extCb.checked = false;
      view.setIncludeExternal(false);
    } else {
      // semantic / others ignore ext toggle
      extCb.disabled = true;
    }
  }

  edgeSel.addEventListener("change", () => {
    view.setEdgeSet(edgeSel.value);
    setExtCheckboxStateFor(edgeSel.value);
  });
  hullsCb.addEventListener("change", () => view.setHulls(hullsCb.checked));
  extCb.addEventListener("change", () => view.setIncludeExternal(extCb.checked));

  // Initialize external checkbox based on the starting set
  setExtCheckboxStateFor(view.edgeKey);

  // ----- Physics card -----
  const cardPhysics = document.createElement("div");
  cardPhysics.className = "pcg-card";
  cardPhysics.innerHTML = `
    <h4>Physics</h4>
    <div class="pcg-row">
      <label for="pcg-charge" style="min-width:70px">Charge</label>
      <input id="pcg-charge" class="pcg-range" type="range" min="-400" max="0" step="1" value="\${view.charge}">
      <input id="pcg-charge-num" class="pcg-num" type="number" min="-400" max="0" step="1" value="\${view.charge}" style="width:70px">
    </div>
    <div class="pcg-row">
      <label for="pcg-link" style="min-width:70px">Link dist</label>
      <input id="pcg-link" class="pcg-range" type="range" min="12" max="220" step="1" value="\${view.linkDistance}">
      <input id="pcg-link-num" class="pcg-num" type="number" min="12" max="220" step="1" value="\${view.linkDistance}" style="width:70px">
    </div>
    <div class="pcg-row">
      <label for="pcg-collide" style="min-width:70px">Collision</label>
      <input id="pcg-collide" class="pcg-range" type="range" min="0" max="40" step="1" value="\${view.collision}">
      <input id="pcg-collide-num" class="pcg-num" type="number" min="0" max="40" step="1" value="\${view.collision}" style="width:70px">
    </div>
    <div class="pcg-row" style="gap:6px">
      <button id="pcg-fit" class="pcg-btn">Fit</button>
      <button id="pcg-pause" class="pcg-btn">Pause</button>
      <button id="pcg-reset" class="pcg-btn primary">Reset</button>
    </div>
    <div class="pcg-row"><span class="pcg-small">Tip: drag to pan, scroll to zoom.</span></div>
  `;
  host.appendChild(cardPhysics);

  const charge   = cardPhysics.querySelector("#pcg-charge");
  const chargeNr = cardPhysics.querySelector("#pcg-charge-num");
  const link     = cardPhysics.querySelector("#pcg-link");
  const linkNr   = cardPhysics.querySelector("#pcg-link-num");
  const collide  = cardPhysics.querySelector("#pcg-collide");
  const collideNr= cardPhysics.querySelector("#pcg-collide-num");
  const btnFit   = cardPhysics.querySelector("#pcg-fit");
  const btnPause = cardPhysics.querySelector("#pcg-pause");
  const btnReset = cardPhysics.querySelector("#pcg-reset");

  function bindPair(rangeEl, numEl, onChange) {
    const sync = (val) => { rangeEl.value = val; numEl.value = val; onChange(Number(val)); };
    rangeEl.addEventListener("input", () => sync(rangeEl.value));
    numEl.addEventListener("input", () => sync(numEl.value));
  }
  bindPair(charge, chargeNr, (v) => view.setCharge(v));
  bindPair(link, linkNr,   (v) => view.setLinkDistance(v));
  bindPair(collide, collideNr, (v) => view.setCollision(v));

  btnFit.addEventListener("click", () => view.fit());
  btnPause.addEventListener("click", () => { const p = view.pause(); btnPause.textContent = p ? "Resume" : "Pause"; });
  btnReset.addEventListener("click", () => {
    edgeSel.value = edgeSel.options[0]?.value || view.edgeKey;
    hullsCb.checked = true;
    link.value = linkNr.value = 48;
    charge.value = chargeNr.value = -45;
    collide.value = collideNr.value = 8;
    view.setEdgeSet(edgeSel.value);
    setExtCheckboxStateFor(edgeSel.value);
    view.setHulls(true);
    view.setLinkDistance(48);
    view.setCharge(-45);
    view.setCollision(8);
    view.fit();
  });

  // ----- Legend / topics -----
  const cardLegend = document.createElement("div");
  cardLegend.className = "pcg-card";
  cardLegend.innerHTML = `<h4>Legend</h4><div class="pcg-legend" id="pcg-legend"></div>`;
  host.appendChild(cardLegend);

  function renderLegend() {
    const info = view.clustersInfo();
    const wrap = cardLegend.querySelector("#pcg-legend");
    wrap.innerHTML = info.map(i => `
      <div class="pcg-swatch" style="background:${i.color}"></div>
      <div class="pcg-name" title="${i.label}">${i.label}</div>
      <div class="pcg-count">${i.size}</div>
    `).join("");
  }
  renderLegend();

  // keyboard quickies
  window.addEventListener("keydown", (e) => {
    if (e.key === " ") { e.preventDefault(); btnPause.click(); }
    if (e.key.toLowerCase() === "f") { e.preventDefault(); btnFit.click(); }
  }, { passive: false });
}
