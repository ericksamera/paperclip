// captures/library/selection.js
// Canonical, idempotent row-selection + keyboard UX for the Library table.
// Works with markup like:
//
// <table class="pc-table" id="pc-table" role="grid" aria-label="Library">
//   <tbody id="pc-body"> <tr class="pc-row" data-id="...">...</tr> ... </tbody>
// </table>
//
// Behavior:
// - Click a row → select it (exclusive)
// - Cmd/Ctrl+click → toggle one
// - Shift+click → range select within the same <tbody>
// - Right-click on an unselected row → selects just that row (so your “Delete” acts on it)
// - ⌘/Ctrl+A → select all visible rows in current <tbody>
// - Esc → clear
// - Delete/Backspace → clicks #pc-bulk-delete if present, else dispatches "pc:delete-selected"
// - Rehydrates after DOM swaps: listens to BOTH "pc:rows-updated" and "pc:rows-replaced"
//
// Safe to import multiple times; it wires only once.

try {
  window.__pcSelectionESM = true;
  window.dispatchEvent(new Event("pc:selection-esm-ready"));
} catch {}

import { $, $$, on } from "./dom.js";

let _wired = false;

// Let legacy code know ESM selection is active, and give it a chance to unbind.


// Find all possible bodies (helps if the table appears in multiple templates)
function bodies() {
  return [
    ...document.querySelectorAll(
      "#pc-body, .pc-table tbody, tbody[data-role='pc-body']"
    ),
  ];
}

// --- Row id helpers ---------------------------------------------------------

function idFromHref(href) {
  if (!href) return "";
  // tolerate /captures/<uuid>/ or /captures/<uuid>/view/
  const m = href.match(/\/captures\/([0-9a-fA-F-]{8,})\/?(?:view)?(?:[?#].*)?$/);
  return m ? m[1] : "";
}

function rowId(tr) {
  if (!tr) return "";
  if (tr.dataset.id && tr.dataset.id.trim()) return tr.dataset.id.trim();

  // common fallbacks
  const fallbacks = ["data-id", "data-pk", "data-uuid", "data-capture-id"];
  for (const name of fallbacks) {
    const v = tr.getAttribute(name);
    if (v && v.trim()) {
      tr.dataset.id = v.trim();
      return tr.dataset.id;
    }
  }
  const a =
    tr.querySelector("a.pc-title[href]") ||
    tr.querySelector('a[href^="/captures/"]') ||
    tr.querySelector('a[href*="/captures/"]');
  const hrefId = idFromHref(a && a.getAttribute("href"));
  if (hrefId) {
    tr.dataset.id = hrefId;
    return hrefId;
  }
  const idFromDomId = (tr.id || "").replace(/^row-/, "");
  if (idFromDomId && idFromDomId !== tr.id) {
    tr.dataset.id = idFromDomId;
    return idFromDomId;
  }
  return "";
}

function normalizeBody(tbody) {
  if (!tbody) return;
  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.classList.add("pc-row");
    tr.setAttribute("role", "row");
    if (!tr.hasAttribute("aria-selected")) {
      tr.setAttribute("aria-selected", "false");
    }
    rowId(tr); // ensure we can address the row later
  });
}
function normalizeAll() {
  bodies().forEach(normalizeBody);
}

// --- State + render ---------------------------------------------------------

const selected = new Set();
let lastId = null;

function renderRow(tr, on) {
  tr.classList.toggle("is-selected", on);
  tr.classList.toggle("selected", on); // legacy class
  tr.setAttribute("aria-selected", on ? "true" : "false");
}
function renderAll() {
  bodies().forEach((tbody) => {
    tbody.querySelectorAll("tr").forEach((tr) => {
      const id = rowId(tr);
      if (id) renderRow(tr, selected.has(id));
    });
  });
  mirrorForLegacy();
  dispatchChanged();
}
function dispatchChanged() {
  document.dispatchEvent(
    new CustomEvent("pc:selection-change", { detail: getSelectedIds() })
  );
}
function findRowById(id) {
  for (const tbody of bodies()) {
    const tr = [...tbody.querySelectorAll("tr")].find((r) => rowId(r) === id);
    if (tr) return tr;
  }
  return null;
}

// Keep window.PCState.selected mirrored for older code
function mirrorForLegacy() {
  const bag = (window.PCState ||= { selected: new Set(), pendingDelete: null });
  bag.selected = new Set(selected);
}

// Read DOM [aria-selected] to rebuild Set (lets other modules flip attributes)
function syncFromDOM() {
  const next = new Set();
  bodies().forEach((tbody) => {
    tbody
      .querySelectorAll('tr[aria-selected="true"]')
      .forEach((tr) => next.add(rowId(tr)));
  });
  const changed =
    next.size !== selected.size || [...next].some((id) => !selected.has(id));
  if (changed) {
    selected.clear();
    next.forEach((id) => selected.add(id));
    lastId = [...selected].pop() || null;
    mirrorForLegacy();
    dispatchChanged();
  }
}

// --- Public-ish helpers -----------------------------------------------------

function selectOnly(id) {
  const before = new Set(selected);
  selected.clear();
  if (id) selected.add(id);
  lastId = id || null;

  const changed = new Set([...before, ...(id ? [id] : [])]);
  changed.forEach((cid) => {
    const tr = findRowById(cid);
    if (tr) renderRow(tr, selected.has(cid));
  });

  mirrorForLegacy();
  dispatchChanged();
}
function toggleOne(id) {
  if (!id) return;
  const wasSelected = selected.has(id);
  if (wasSelected) selected.delete(id); else selected.add(id);
  lastId = id;

  const tr = findRowById(id);
  if (tr) renderRow(tr, !wasSelected);

  mirrorForLegacy();
  dispatchChanged();
}
function selectRangeBetween(tbody, aId, bId) {
  if (!tbody || !aId || !bId) return;
  const rows = [...tbody.querySelectorAll("tr")];
  const idx = {};
  rows.forEach((tr, i) => (idx[rowId(tr)] = i));
  const ai = idx[aId], bi = idx[bId];
  if (ai == null || bi == null) return;

  const [lo, hi] = ai < bi ? [ai, bi] : [bi, ai];
  const changedIds = [];
  for (let i = lo; i <= hi; i++) {
    const id = rowId(rows[i]); if (!id) continue;
    if (!selected.has(id)) { selected.add(id); changedIds.push(id); }
  }

  changedIds.forEach((cid) => {
    const tr = findRowById(cid);
    if (tr) renderRow(tr, true);
  });

  mirrorForLegacy();
  dispatchChanged();
}

export function clearSelection() {
  if (!selected.size) return;
  const changed = [...selected];
  selected.clear();
  lastId = null;

  changed.forEach((cid) => {
    const tr = findRowById(cid);
    if (tr) renderRow(tr, false);
  });

  mirrorForLegacy();
  dispatchChanged();
}
export function getSelectedIds() {
  return [...selected];
}

export function openCurrent(kind) {
  const tr =
    (lastId && findRowById(lastId)) ||
    bodies()[0]?.querySelector("tr.pc-row");
  if (!tr) return;
  if (kind === "detail") {
    window.location.href = `/captures/${tr.dataset.id}/`;
  } else if (kind === "doi_or_url") {
    const href = tr.dataset.doiUrl || tr.dataset.url;
    if (href) window.open(href, "_blank", "noopener");
  }
}
export function copyDoi() {
  const tr = lastId && findRowById(lastId);
  const doi = tr?.dataset?.doi;
  if (doi && navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(doi);
  }
}

// --- Events ----------------------------------------------------------------

function isEditableTarget(t) {
  const tag = (t && t.tagName) ? t.tagName.toLowerCase() : "";
  return (
    t?.isContentEditable ||
    tag === "input" ||
    tag === "textarea" ||
    tag === "select"
  );
}
function rowFromEventTarget(t) {
  if (!t?.closest) return null;
  const tr = t.closest("tr");
  return tr && bodies().some((b) => b.contains(tr)) ? tr : null;
}

function onClick(e) {
  if (e.button !== 0) return; // left click only
  if (isEditableTarget(e.target)) return;
  if (e.target.closest("a,button,summary,label,input,textarea,select")) return;
  const sel = window.getSelection?.().toString() || "";
  if (sel.trim()) return;

  const tr = rowFromEventTarget(e.target);
  if (!tr) return;
  const id = rowId(tr);
  if (!id) return;

  if (e.shiftKey && lastId) {
    const lastRow = findRowById(lastId);
    if (lastRow && lastRow.closest("tbody") === tr.closest("tbody")) {
      selected.add(lastId);
      selected.add(id);
      selectRangeBetween(tr.closest("tbody"), lastId, id);
      lastId = id;
      return;
    }
  }
  if (e.metaKey || e.ctrlKey) {
    toggleOne(id);
  } else {
    selectOnly(id);
  }
}

// NEW: right-click selects target row (so your Delete acts on that row)
// We intentionally DO NOT preventDefault — if you use a custom menu elsewhere,
// it will still open.
function onContextMenu(e) {
  if (isEditableTarget(e.target)) return;
  const tr = rowFromEventTarget(e.target);
  if (!tr) return;
  const id = rowId(tr);
  if (!id) return;
  if (!selected.has(id)) {
    // select just that row so the context action applies to it
    selectOnly(id);
  }
}

function onKeydown(e) {
  if (isEditableTarget(e.target)) return;

  // Cmd/Ctrl+A → select all in current tbody
  if ((e.key === "a" || e.key === "A") && (e.metaKey || e.ctrlKey)) {
    const b = bodies()[0];
    if (!b) return;
    e.preventDefault();
    selected.clear();
    b.querySelectorAll("tr").forEach((tr) => {
      const id = rowId(tr);
      if (id) selected.add(id);
    });
    renderAll();
    return;
  }

  // Esc → clear
  if (e.key === "Escape") {
    e.preventDefault();
    clearSelection();
    return;
  }

  // Delete / Backspace → click the bulk-delete control if present,
  // otherwise broadcast a delete intent with selected ids.
  if ((e.key === "Delete" || e.key === "Backspace") && selected.size) {
    e.preventDefault();
    const btn = document.getElementById("pc-bulk-delete");
    if (btn) {
      btn.click();
    } else {
      document.dispatchEvent(
        new CustomEvent("pc:delete-selected", { detail: getSelectedIds() })
      );
    }
  }
}

// MutationObserver: renormalize and keep Set in sync with aria flips
let mo;
function wireMutationObserver() {
  if (mo) mo.disconnect();
  mo = new MutationObserver((mutations) => {
    let touched = false,
      attrs = false;
    for (const m of mutations) {
      if (m.type === "childList") {
        const added = [...m.addedNodes].filter((n) => n.nodeType === 1);
        for (const n of added) {
          if (
            n.matches?.("#pc-body, .pc-table tbody, tbody[data-role='pc-body']") ||
            n.querySelector?.("#pc-body, .pc-table tbody, tbody[data-role='pc-body']")
          ) {
            touched = true;
          }
        }
      } else if (m.type === "attributes" && m.attributeName === "aria-selected") {
        attrs = true;
      }
    }
    if (touched) {
      normalizeAll();
      renderAll();
    }
    if (attrs) {
      syncFromDOM();
    }
  });
  mo.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["aria-selected"],
  });
}

// --- Init ------------------------------------------------------------------

export function initSelection() {
  if (_wired) return;
  _wired = true;

  
  try { window.__pcESMSelectionReady = true; } catch(_) {}
normalizeAll();
  syncFromDOM();
  renderAll();

  on(document, "click", onClick);
  on(document, "contextmenu", onContextMenu);
  on(document, "keydown", onKeydown);

  // Rehydrate on both event names (different modules may emit either)
  document.addEventListener("pc:rows-updated", () => {
    normalizeAll();
    syncFromDOM();
    renderAll();
  });
  document.addEventListener("pc:rows-replaced", () => {
    normalizeAll();
    syncFromDOM();
    renderAll();
  });

  wireMutationObserver();

  // Debug bridge
  window.pcSelection = {
    get ids() {
      return getSelectedIds();
    },
    clear: clearSelection,
    selectOnlyId: selectOnly,
    syncFromDOM,
  };
}

// ===== Hotkeys: j/k and ArrowUp/ArrowDown for Library rows (safe, idempotent) =====
(() => {
  // Prevent double binding across reloads
  let __pcHotkeysBound = false;

  function isEditable(el) {
    if (!el) return false;
    if (el.isContentEditable) return true;
    const tag = el.tagName;
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
  }

  function getRows() {
    const tbody = document.querySelector('#z-table tbody') || document.querySelector('tbody');
    if (!tbody) return [];
    // support both modern and legacy row classes
    return Array.from(tbody.querySelectorAll('tr.pc-row, tr[data-row="pc-row"]'));
  }

  function getCurrent(rows) {
    // try common selected markers in order
    const candidate =
      document.querySelector('tr.pc-row.is-selected') ||
      document.querySelector('tr.pc-row.selected') ||
      document.querySelector('tr.pc-row[aria-selected="true"]') ||
      document.querySelector('tr[data-selected="true"]');
    if (!candidate) return { el: null, idx: -1 };
    const idx = rows.indexOf(candidate);
    return { el: candidate, idx };
  }

  function move(delta) {
    const rows = getRows();
    if (!rows.length) return;

    const { el: current, idx } = getCurrent(rows);
    let nextIdx = idx >= 0 ? idx + delta : (delta > 0 ? 0 : rows.length - 1);
    if (nextIdx < 0) nextIdx = 0;
    if (nextIdx >= rows.length) nextIdx = rows.length - 1;

    const next = rows[nextIdx];
    if (!next || next === current) return;

    // Scroll into view and simulate a click so existing selection logic runs
    try { next.scrollIntoView({ block: 'nearest' }); } catch {}
    next.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    // Also move focus for accessibility
    next.setAttribute('tabindex', '-1');
    try { next.focus({ preventScroll: true }); } catch {}
  }

  function onKeydown(e) {
    if (e.defaultPrevented) return;
    if (isEditable(e.target)) return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;

    const k = e.key;
    if (k === 'j' || k === 'ArrowDown') {
      e.preventDefault();
      move(+1);
    } else if (k === 'k' || k === 'ArrowUp') {
      e.preventDefault();
      move(-1);
    }
  }

  // Bind once on DOM ready
  function bind() {
    if (__pcHotkeysBound) return;
    __pcHotkeysBound = true;
    document.addEventListener('keydown', onKeydown, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind, { once: true });
  } else {
    bind();
  }
})();
/// ===== end hotkeys =====