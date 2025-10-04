// services/server/paperclip/static/captures/library/columns_panels.js
import { $, $$, on } from "./dom.js";
import { clearSelection, openCurrent, copyDoi } from "./selection.js";

/* ───────────────────────── Column prefs ───────────────────────── */

const ALL_COLS = ["title", "authors", "year", "journal", "doi", "added", "refs"];
const LABEL = {
  title: "Title",
  authors: "Authors",
  year: "Year",
  journal: "Journal",
  doi: "DOI",
  added: "Added",
  refs: "Refs",
};

const DEFAULT_COLS = {
  order: [...ALL_COLS],
  show: { title: true, authors: true, year: true, journal: true, doi: false, added: true, refs: true },
  widths: { authors: "16", year: "6", journal: "24", doi: "24", added: "10", refs: "6" },
};

// Read + normalize older saved shapes (no order, etc.)
function readCols() {
  let cfg;
  try {
    cfg = JSON.parse(localStorage.getItem("pcCols") || "") || DEFAULT_COLS;
  } catch (_) {
    cfg = DEFAULT_COLS;
  }
  // Ensure all keys exist and order is sane
  cfg.order = Array.isArray(cfg.order) ? cfg.order.filter(k => ALL_COLS.includes(k)) : [...ALL_COLS];
  // add any missing keys at the end (forward‑compat)
  for (const k of ALL_COLS) if (!cfg.order.includes(k)) cfg.order.push(k);
  // never hide title
  cfg.show = cfg.show || {};
  cfg.show.title = true;
  for (const k of ALL_COLS) if (typeof cfg.show[k] === "undefined") cfg.show[k] = true;
  cfg.widths = cfg.widths || {};
  return cfg;
}
function saveCols(cfg) {
  try { localStorage.setItem("pcCols", JSON.stringify(cfg)); } catch (_) {}
}

// Reorder the DOM for header + all rows to match the given 'order'
function reorderTable(order) {
  const table = $("#pc-table");
  if (!table) return;

  const safeOrder = order.filter(k => ALL_COLS.includes(k));
  const finalOrder = ["title", ...safeOrder.filter(k => k !== "title")];

  const theadRow = table.querySelector("thead tr");
  const bodyRows = $$("#pc-body tr.pc-row");

  function applyToRow(tr) {
    const cells = {};
    tr.querySelectorAll("[data-col]").forEach((td) => {
      cells[td.getAttribute("data-col")] = td;
    });

    // Always keep the gear column (if present) as the last cell
    const gear = tr.querySelector(".pc-col-gear");
    if (gear && gear.parentElement === tr) tr.appendChild(gear);

    // Re-append known columns in saved order
    for (const key of finalOrder) {
      if (cells[key]) tr.appendChild(cells[key]);
    }
  }

  if (theadRow) applyToRow(theadRow);
  bodyRows.forEach(applyToRow);
}


// Show/hide + widths + reorder
function applyCols(cfg) {
  // 1) Reorder table to saved order
  reorderTable(cfg.order);

  // 2) Show/hide
  for (const key of ALL_COLS) {
    const onFlag = key === "title" ? true : !!cfg.show[key];
    $$(`[data-col="${key}"]`).forEach((el) => { el.style.display = onFlag ? "" : "none"; });
  }

  // 3) Widths (in ch)
  for (const [key, val] of Object.entries(cfg.widths || {})) {
    const ch = String(val || "").trim();
    $$(`[data-col="${key}"]`).forEach((el) => (el.style.width = ch ? ch + "ch" : ""));
  }
}

/* ───────────────────────── Drawer UI ───────────────────────── */

function drawer() { return $("#pc-cols-drawer"); }
function listEl() { return $("#pc-cols-list"); }
function isOpen() { return drawer()?.classList.contains("open"); }

function openDrawer() {
  const d = drawer();
  if (!d) return;
  d.classList.add("open");
  d.setAttribute("aria-hidden", "false");
}

function closeDrawer() {
  const d = drawer();
  if (!d) return;
  d.classList.remove("open");
  d.setAttribute("aria-hidden", "true");
}

function buildListItem(key, cfg) {
  const li = document.createElement("li");
  li.className = "pc-cols-item";
  li.dataset.key = key;

  const fixed = key === "title";
  if (fixed) li.dataset.fixed = "1";
  li.draggable = !fixed;

  // Only start drag when grabbing the handle (prevents accidental drags on checkbox/label)
  li.addEventListener("dragstart", (e) => {
    if (!e.target.closest(".handle") || fixed) { e.preventDefault(); return; }
    li.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", key); } catch (_) {}
  });
  li.addEventListener("dragend", () => li.classList.remove("dragging"));

  li.innerHTML = `
    <span class="handle" title="Drag to reorder" aria-hidden="true">☰</span>
    <input type="checkbox" ${fixed ? "checked disabled" : (cfg.show[key] ? "checked" : "")} data-col-toggle="${key}">
    <span class="label">${LABEL[key] || key}</span>
  `;

  // Toggle handler
  const cb = li.querySelector("input[type=checkbox]");
  on(cb, "change", () => {
    if (fixed) return;
    cfg.show[key] = !!cb.checked;
    saveCols(cfg);
    applyCols(cfg);
  });

  return li;
}

function getDragAfterElement(container, y) {
  const items = [...container.querySelectorAll(".pc-cols-item:not(.dragging)")];
  return items.reduce(
    (closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      return offset < 0 && offset > closest.offset ? { offset, element: child } : closest;
    },
    { offset: Number.NEGATIVE_INFINITY, element: null }
  ).element;
}

function initColsDrawerUI() {
  const cfg = readCols();

  // Populate list in saved order
  const list = listEl();
  if (!list) return;
  list.innerHTML = "";
  for (const key of cfg.order) {
    list.appendChild(buildListItem(key, cfg));
  }

  // Drag & drop within the list
  on(list, "dragover", (e) => {
    e.preventDefault();
    const dragging = list.querySelector(".pc-cols-item.dragging");
    if (!dragging) return;
    const after = getDragAfterElement(list, e.clientY);
    if (after == null) list.appendChild(dragging);
    else list.insertBefore(dragging, after);
  });

  on(list, "drop", () => {
    // Persist new order from DOM
    const domOrder = [...list.querySelectorAll(".pc-cols-item")].map((li) => li.dataset.key);
    // Pin title to the first position for table layout stability
    const next = ["title", ...domOrder.filter((k) => k !== "title")];
    cfg.order = next.filter((k) => ALL_COLS.includes(k));
    saveCols(cfg);
    applyCols(cfg);
  });

  // Reset
  const resetBtn = $("#pc-cols-reset");
  on(resetBtn, "click", () => {
    saveCols(DEFAULT_COLS);
    applyCols(DEFAULT_COLS);
    initColsDrawerUI(); // rebuild list to reflect defaults
  });

  // Initial apply (ensures drawer reflects current table)
  applyCols(cfg);
}

/* ───────────────────────── Splitters & pane toggles ───────────────────────── */

// Same UX as before (kept intact so nothing else breaks)
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

/* ───────────────────────── Public init ───────────────────────── */

export function initPanelsAndColumns() {
  // Drawer wiring
  const triggers = $$("#pc-cols-toggle, #pc-cols-toggle-table, [data-act='toggle-columns']");
  const closeBtn = $("#pc-cols-close");
  const backdrop = $("#pc-cols-drawer-backdrop");

  triggers.forEach(btn => on(btn, "click", () => {
    openDrawer();
    initColsDrawerUI();
  }));
  on(closeBtn, "click", closeDrawer);
  on(backdrop, "click", closeDrawer);
  on(window, "keydown", (e) => { if (e.key === "Escape" && isOpen()) { e.preventDefault(); closeDrawer(); } });

  // Apply on tbody swaps (search/paging/infinite scroll)
  on(document, "pc:rows-updated", () => applyCols(readCols()));

  // Left/Right toggles (unchanged)
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

  // Hotkeys (unchanged)
  on(window, "keydown", (e) => {
    const tag = (e.target && (e.target.tagName || "")).toLowerCase();
    const typing = tag === "input" || tag === "textarea" || e.target.isContentEditable;
    if (!typing && e.key.toLowerCase() === "c") { e.preventDefault(); (triggers[0] || document.body).click(); return; }
  });

  // First load: apply saved prefs
  applyCols(readCols());
}
