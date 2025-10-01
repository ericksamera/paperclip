import { $, $$, on } from "./dom.js";
import { clearSelection, openCurrent, copyDoi } from "./selection.js";

const DEFAULT_COLS = {
  show: { title:true, authors:true, year:true, journal:true, doi:false, added:true, refs:true },
  widths: { authors:"16", year:"6", journal:"24", doi:"24", added:"10", refs:"6" }
};
function readCols(){
  try { return JSON.parse(localStorage.getItem("pcCols") || "") || DEFAULT_COLS; }
  catch(_) { return DEFAULT_COLS; }
}
function saveCols(cfg){ try { localStorage.setItem("pcCols", JSON.stringify(cfg)); } catch(_) {} }
function applyCols(cfg){
  const cols = ["title","authors","year","journal","doi","added","refs"];
  cols.forEach(key => {
    const onFlag = (key === "title") ? true : !!cfg.show[key];
    $$(`[data-col="${key}"]`).forEach(el => { el.style.display = onFlag ? "" : "none"; });
  });
  Object.entries(cfg.widths || {}).forEach(([key, val]) => {
    const ch = String(val || "").trim();
    $$(`[data-col="${key}"]`).forEach(el => el.style.width = ch ? (ch + "ch") : "");
  });
}

function makeSplitter(id, varName, minPx, maxPx, storeKey) {
  const shell = document.getElementById("z-shell");
  const el = document.getElementById(id);
  if (!el || !shell) return;
  let dragging = false, startX = 0, startW = 0;
  on(el, "mousedown", (e) => {
    dragging = true;
    startX = e.clientX;
    startW = parseInt(getComputedStyle(shell).getPropertyValue(varName), 10) || 0;
    document.body.style.userSelect = "none";
  });
  on(window, "mousemove", (e) => {
    if (!dragging) return;
    let delta = e.clientX - startX;
    let next = varName === "--right-w" ? (startW - delta) : (startW + delta);
    next = Math.max(minPx, Math.min(maxPx, next));
    shell.style.setProperty(varName, next + "px");
  });
  on(window, "mouseup", () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.userSelect = "";
    const cur = getComputedStyle(shell).getPropertyValue(varName).trim();
    localStorage.setItem(storeKey, cur);
  });
  const saved = localStorage.getItem(storeKey);
  if (saved) shell.style.setProperty(varName, saved);
}

export function initPanelsAndColumns() {
  // Columns UI
  const colsBtn   = $("#pc-cols-toggle");
  const colsPanel = $("#pc-cols-panel");
  const colsClose = $("#pc-cols-close");
  const colsReset = $("#pc-cols-reset");

  function initColsUI(){
    const cfg = readCols();
    $$("[data-col-toggle]").forEach(cb => {
      const k = cb.getAttribute("data-col-toggle");
      cb.checked = (k === "title") ? true : !!cfg.show[k];
      on(cb, "change", () => { if (k !== "title") { cfg.show[k] = cb.checked; saveCols(cfg); applyCols(cfg); }});
    });
    $$("[data-col-width]").forEach(inp => {
      const k = inp.getAttribute("data-col-width");
      inp.value = (cfg.widths[k] || "");
      on(inp, "input", () => { cfg.widths[k] = inp.value.replace(/[^\d.]/g, ""); saveCols(cfg); applyCols(cfg); });
    });
    on(colsReset, "click", () => { saveCols(DEFAULT_COLS); applyCols(DEFAULT_COLS); initColsUI(); });
    applyCols(cfg);
  }
  on(colsBtn,   "click", () => { const vis = colsPanel.style.display !== "block"; colsPanel.style.display = vis ? "block" : "none"; if (vis) initColsUI(); });
  on(colsClose, "click", () => { colsPanel.style.display = "none"; });
  on(document,  "pc:rows-updated", () => applyCols(readCols()));

  // Left / Right toggles
  const shell = document.getElementById("z-shell");
  const toggleRightBtn = document.getElementById("z-toggle-right");
  const toggleLeftBtn  = document.getElementById("z-toggle-left");

  function openRight() { shell?.style.setProperty("--right-w", localStorage.getItem("pc-right-w") || "360px"); }
  function closeRight(){ localStorage.setItem("pc-right-w", getComputedStyle(shell).getPropertyValue("--right-w").trim() || "360px"); shell?.style.setProperty("--right-w", "0px"); }
  function openLeft(){  shell?.style.setProperty("--left-w", localStorage.getItem("pc-left-w") || "260px"); localStorage.setItem("pc-left-hidden", "0"); }
  function closeLeft(){ localStorage.setItem("pc-left-w",  getComputedStyle(shell).getPropertyValue("--left-w").trim() || "260px"); shell?.style.setProperty("--left-w", "0px"); localStorage.setItem("pc-left-hidden", "1"); }

  on(toggleRightBtn, "click", () => {
    const w = getComputedStyle(shell).getPropertyValue("--right-w").trim();
    (w === "0px" || w === "0") ? openRight() : closeRight();
  });
  on(toggleLeftBtn, "click", () => {
    const w = getComputedStyle(shell).getPropertyValue("--left-w").trim();
    (w === "0px" || w === "0") ? openLeft() : closeLeft();
  });

  // Splitters + persisted left hidden state
  makeSplitter("z-splitter-left",  "--left-w",  160, 480, "pc-left-w");
  makeSplitter("z-splitter-right", "--right-w", 0,   560, "pc-right-w");
  if (localStorage.getItem("pc-left-hidden") === "1") shell?.style.setProperty("--left-w", "0px");

  // Hotkeys (only when not typing)
  on(window, "keydown", (e) => {
    const tag = (e.target && (e.target.tagName || "")).toLowerCase();
    const typing = tag === "input" || tag === "textarea" || e.target.isContentEditable;

    if (!typing && e.key === "/") { e.preventDefault(); document.querySelector(".z-search input[name=q]")?.focus(); return; }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "a") { e.preventDefault(); $$("#pc-body tr.pc-row").forEach(r => r.setAttribute("aria-selected", "true")); return; }
    if (!typing && (e.key === "Delete" || e.key === "Backspace")) { e.preventDefault(); document.getElementById("pc-bulk-delete")?.click(); return; }
    if (!typing && e.key === "Escape") { e.preventDefault(); clearSelection(); return; }
    if (!typing && e.key.toLowerCase() === "c") { e.preventDefault(); document.getElementById("pc-cols-toggle")?.click(); return; }
    if (!typing && e.key.toLowerCase() === "i") { e.preventDefault(); document.getElementById("z-toggle-right")?.click(); return; }
    if (!typing && (e.key === "Enter")) { e.preventDefault(); openCurrent("detail"); return; }
    if (!typing && e.key.toLowerCase() === "o") { e.preventDefault(); openCurrent("doi_or_url"); return; }
    if (!typing && e.key.toLowerCase() === "y") { e.preventDefault(); copyDoi(); return; }
  });
}
