import { $, $$, on, escapeHtml } from "./dom.js";
import { state } from "./state.js";

const tbody = document.getElementById("pc-body");
const bulkBtn = document.getElementById("pc-bulk-delete");
const info = document.getElementById("z-info");

function updateBulk() {
  if (!bulkBtn) return;
  bulkBtn.disabled = state.selected.size === 0;
  bulkBtn.textContent = state.selected.size ? `Delete (${state.selected.size})` : "Delete selected";
}

function setRowSelected(tr, onFlag) {
  if (!tr?.dataset?.id) return;
  const next = onFlag ?? (tr.getAttribute("aria-selected") !== "true");
  tr.setAttribute("aria-selected", next ? "true" : "false");
  if (next) state.selected.add(tr.dataset.id);
  else state.selected.delete(tr.dataset.id);
  updateBulk();
  if (next) renderDetailsFromRow(tr);
}

export function clearSelection() {
  $$("tr.pc-row[aria-selected='true']", tbody).forEach(tr => setRowSelected(tr, false));
}

function lastSelectedRow() {
  const ids = Array.from(state.selected);
  if (!ids.length) return null;
  return tbody.querySelector(`tr.pc-row[data-id="${CSS.escape(ids[ids.length - 1])}"]`);
}

function truncate(s, n) { return (s && s.length > n) ? (s.slice(0, n - 1) + "…") : s; }
function safeHostname(u) { try { return new URL(u, location.href).hostname; } catch { return ""; } }

function renderDetailsFromRow(tr) {
  if (!info) return;
  const title  = tr.dataset.title || "(Untitled)";
  const url    = tr.dataset.url || "";
  const site   = safeHostname(url);
  const auth   = tr.dataset.authors || "";
  const jour   = tr.dataset.journal || "";
  const year   = tr.dataset.year || "";
  const doi    = tr.dataset.doi || "";
  const doiUrl = tr.dataset.doiUrl || "";
  const abs    = tr.dataset.abstract || "";
  const kws    = (tr.dataset.keywords || "").split(",").map(s => s.trim()).filter(Boolean);

  info.innerHTML = `
    <h3>${escapeHtml(title)}</h3>
    <div class="z-meta">${jour ? escapeHtml(jour) + " · " : ""}${year ? year + " · " : ""}${site ? escapeHtml(site) : ""}</div>
    ${auth ? `<div class="z-meta">${escapeHtml(auth)}</div>` : ""}
    ${doi ? `<div class="z-meta"><a href="${escapeHtml(doiUrl || ("https://doi.org/" + doi))}" target="_blank" rel="noopener">${escapeHtml(doi)}</a></div>` : ""}
    ${abs ? `<div class="z-meta"><strong>Abstract.</strong> ${escapeHtml(truncate(abs, 700))}</div>` : ""}
    ${kws.length ? `<div class="z-kws">${kws.map(k => `<span class="z-kw">${escapeHtml(k)}</span>`).join("")}</div>` : ""}
  `;
  // ensure right pane is visible if user collapsed it earlier
  const shell = document.getElementById("z-shell");
  if (shell) shell.style.setProperty("--right-w", localStorage.getItem("pc-right-w") || "360px");
}

export function openCurrent(kind) {
  const tr = lastSelectedRow() || tbody.querySelector("tr.pc-row");
  if (!tr) return;
  if (kind === "detail") window.location.href = `/captures/${tr.dataset.id}/`;
  else if (kind === "doi_or_url") {
    const href = tr.dataset.doiUrl || tr.dataset.url;
    if (href) window.open(href, "_blank", "noopener");
  }
}
export function copyDoi() {
  const tr = lastSelectedRow(); if (!tr) return;
  const doi = tr.dataset.doi; if (!doi) return;
  navigator.clipboard?.writeText(doi).catch(() => {});
}

function ensureRowsDraggable() {
  $$("#pc-body tr.pc-row").forEach(r => r.setAttribute("draggable", "true"));
}

const rows = () => $$("tr.pc-row", tbody);
const rowIndex = (tr) => rows().indexOf(tr);

// anchor for shift-range selection
let anchorIndex = null;

export function initSelection() {
  if (!tbody) return;

  // Single / toggle / range selection on CLICK
  on(tbody, "click", (e) => {
    const tr = e.target.closest("tr.pc-row");
    if (!tr || e.target.closest("a")) return;

    const isShift   = !!e.shiftKey;
    const isCtrlCmd = !!(e.ctrlKey || e.metaKey);

    if (isShift && anchorIndex !== null) {
      // Shift-click = select contiguous range from the anchor row
      const all = rows();
      const i = rowIndex(tr);
      const [a, b] = i < anchorIndex ? [i, anchorIndex] : [anchorIndex, i];
      clearSelection();
      all.slice(a, b + 1).forEach(r => setRowSelected(r, true));
      // keep anchor where it was (common list behavior)
    } else if (isCtrlCmd) {
      // Ctrl/Cmd-click = toggle just this row (keep others)
      setRowSelected(tr);
      anchorIndex = rowIndex(tr);
    } else {
      // Plain click = replace selection with just this row
      clearSelection();
      setRowSelected(tr, true);
      anchorIndex = rowIndex(tr);
    }
  });

  // Update anchor on mousedown so Shift-click knows where to start,
  // but only set it when not using modifiers (matches list UIs).
  on(tbody, "mousedown", (e) => {
    const tr = e.target.closest("tr.pc-row"); if (!tr) return;
    if (!e.shiftKey && !(e.ctrlKey || e.metaKey)) {
      anchorIndex = rowIndex(tr);
    }
  });

  // Drag start → package selected ids (or the single row) for DnD to the Collections rail
  on(tbody, "dragstart", (e) => {
    const tr = e.target.closest("tr.pc-row"); if (!tr) return;
    // If the dragged row isn’t already selected, single-select it
    if (!state.selected.size || !state.selected.has(tr.dataset.id)) {
      clearSelection();
      setRowSelected(tr, true);
      anchorIndex = rowIndex(tr);
    }
    const ids = Array.from(state.selected);
    const payload = JSON.stringify({ type: "pc-ids", ids });
    try {
      e.dataTransfer?.setData("application/json", payload);
      e.dataTransfer?.setData("text/plain", payload);
      e.dataTransfer.effectAllowed = "copyMove";
      // Drag ghost
      const ghost = document.createElement("div");
      ghost.className = "pc-drag-ghost";
      ghost.textContent = `${ids.length} item${ids.length > 1 ? "s" : ""}`;
      ghost.style.cssText = "position:absolute;top:-9999px;left:-9999px;padding:6px 8px;background:rgba(0,0,0,.85);color:#fff;border-radius:6px;font:12px system-ui, sans-serif;";
      document.body.appendChild(ghost);
      e.dataTransfer.setDragImage(ghost, -10, -10);
      setTimeout(() => ghost.remove(), 0);
    } catch (_) {}
    // Suppress text selection while dragging
    document.body.style.userSelect = "none";
  });
  on(tbody, "dragend", () => { document.body.style.userSelect = ""; });

  // When rows are re-rendered (search / paging), drop selection and (re)enable draggable
  on(document, "pc:rows-updated", () => { clearSelection(); ensureRowsDraggable(); });
  ensureRowsDraggable();
  updateBulk();
}
