// services/server/paperclip/static/captures/library/selection.js
// Canonical, idempotent selection for the Library table.
// – Single-click = select only that row
// – Cmd/Ctrl-click = toggle one row
// – Shift-click = select a contiguous range (anchor = last single/clicked)
// – Click on whitespace in the table area = clear selection
// – Delete/Backspace = trigger bulk delete button once (no double toast)

import { $, $$, qsa, on } from "./dom.js";
import { EVENTS, emitSelectionChange } from "./events.js";

let tbody = null;
let anchorIndex = -1;                // for shift-range
const selected = new Set();          // ids (string)

// ---------- helpers ----------
function ensureTbody() {
  // Prefer explicit body; fall back to first tbody.
  tbody =
    document.getElementById("pc-body") ||
    $("#pc-table tbody") ||
    $("tbody");
}
function rows() {
  return Array.from(tbody?.querySelectorAll("tr.pc-row[data-id]") || []);
}
function rowIndex(tr) {
  const all = rows();
  return all.indexOf(tr);
}
function setRowSelected(tr, on) {
  if (!tr || !tr.dataset.id) return;
  const willSelect = on === undefined ? tr.getAttribute("aria-selected") !== "true" : !!on;
  tr.setAttribute("aria-selected", willSelect ? "true" : "false");
  tr.classList.toggle("pc-row--selected", willSelect);
  if (willSelect) selected.add(tr.dataset.id);
  else selected.delete(tr.dataset.id);
}
function clearSelection() {
  rows().forEach(tr => {
    tr.setAttribute("aria-selected", "false");
    tr.classList.remove("pc-row--selected");
  });
  selected.clear();
  emitSelectionChange({ ids: [] });
}
function selectOnly(tr) {
  clearSelection();
  setRowSelected(tr, true);
  anchorIndex = rowIndex(tr);
  emitSelectionChange({ ids: getSelectedIds() });
}
function selectRange(toTr) {
  const all = rows();
  if (anchorIndex < 0) anchorIndex = rowIndex(toTr);
  const from = Math.min(anchorIndex, rowIndex(toTr));
  const to   = Math.max(anchorIndex, rowIndex(toTr));
  clearSelection();
  for (let i = from; i <= to; i++) setRowSelected(all[i], true);
  emitSelectionChange({ ids: getSelectedIds() });
}
function getSelectedIds() { return Array.from(selected); }

// ---------- event wiring ----------
function bindDelegatedClick() {
  if (!tbody) return;

  // Normalize any server-rendered rows (role + aria)
  qsa("tr[data-id]", tbody).forEach(tr => {
    tr.classList.add("pc-row");
    if (!tr.hasAttribute("aria-selected")) tr.setAttribute("aria-selected", "false");
  });

  // Click on a row
  on(tbody, "click", (e) => {
    // Ignore native interactive controls
    if (e.target.closest("a, button, input, textarea, label, [contenteditable]")) return;

    const tr = e.target.closest("tr.pc-row[data-id]");
    if (!tr) return;

    if (e.shiftKey) {
      selectRange(tr);
      return;
    }

    if (e.metaKey || e.ctrlKey) {
      // Toggle just this row (don’t affect others)
      setRowSelected(tr, undefined);
      anchorIndex = rowIndex(tr);
      emitSelectionChange({ ids: getSelectedIds() });
      return;
    }

    // Plain click → single-select
    selectOnly(tr);
  });

  // Click outside rows inside the scroll area clears selection
  on(tbody, "click", (e) => {
    const tr = e.target.closest("tr.pc-row[data-id]");
    if (!tr) clearSelection();
  });
}

function bindHotkeys() {
  // Make sure we bind only once across re-initializations
  if (window.__pcDeleteHotkeyWired) return;
  window.__pcDeleteHotkeyWired = true;

  document.addEventListener(
    "keydown",
    (e) => {
      if (e.defaultPrevented) return;
      if (e.key === "Delete" || e.key === "Backspace") {
        const btn = $("#pc-bulk-delete");
        if (!btn) return;
        if (!getSelectedIds().length) return;
        e.preventDefault();
        e.stopPropagation();
        btn.click(); // bulk_delete.js owns the flow + toast
      }
    },
    { capture: true }
  );
}

export function initSelection() {
  ensureTbody();
  if (!tbody) return;
  bindDelegatedClick();
  bindHotkeys();
  emitSelectionChange({ ids: getSelectedIds() }); // initial state broadcast
}
