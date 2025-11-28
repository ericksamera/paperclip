// services/server/paperclip/static/captures/library/index.js
// Single entry for the Library UI, wired feature-first.
//
// infra/    → shared helpers (dom/events/state/http…)
// features/ → behaviors (selection, bulk delete, search, …)
//
// NOTE: CSS is linked from the template; do not import CSS here.

import "./infra/events.js"; // sets up canonical row events + legacy bridge

import { initSelection } from "./features/selection.js";
import { initBulkDelete } from "./features/bulk_delete.js";
import { initSearchAndPaging, ensureInitialRows } from "./features/search_paging.js";
import { initCollectionsAndContextMenus } from "./features/collections_ctx_dnd.js";
import { initDetailsPanel } from "./features/details_panel.js";
import { initPanelsAndColumns } from "./features/columns_panels.js";
import { initHoverPrefetch } from "./features/hover_prefetch.js";
import { initGroups } from "./features/groups.js";
import { initYearsWidget } from "./features/years_hist.js";

function initDiagnosticsToggle() {
  const sidebarBtn = document.getElementById("z-toggle-left");
  if (!sidebarBtn) return;
  const parent = sidebarBtn.parentElement;
  if (!parent || parent.__pcDiagWired) return;
  parent.__pcDiagWired = true;

  const btn = document.createElement("button");
  btn.type = "button";
  btn.id = "pc-diag-toggle";
  btn.className = "btn";
  btn.title = "Toggle diagnostics overlay";

  function isOn() {
    const url = new URL(location.href);
    const hasParam = url.searchParams.has("diag");
    let stored = false;
    try {
      stored = localStorage.getItem("pcDiag") === "1";
    } catch {
      stored = false;
    }
    return hasParam || stored;
  }

  function refreshLabel() {
    btn.textContent = isOn() ? "Diagnostics ✓" : "Diagnostics";
  }

  function toggleDiagnostics() {
    const url = new URL(location.href);
    const on = isOn();
    try {
      if (on) {
        url.searchParams.delete("diag");
        localStorage.removeItem("pcDiag");
        localStorage.removeItem("pc-diag");
      } else {
        url.searchParams.set("diag", "1");
        localStorage.setItem("pcDiag", "1");
        localStorage.setItem("pc-diag", "1");
      }
    } catch {
      // If localStorage fails, at least use the URL param
      if (on) {
        url.searchParams.delete("diag");
      } else {
        url.searchParams.set("diag", "1");
      }
    }
    location.href = url.toString();
  }

  btn.addEventListener("click", () => {
    toggleDiagnostics();
  });

  refreshLabel();
  parent.insertBefore(btn, sidebarBtn);

  // Alt+D toggles diagnostics
  window.addEventListener("keydown", (e) => {
    const typing =
      e.target &&
      (e.target.tagName === "INPUT" ||
        e.target.tagName === "TEXTAREA" ||
        e.target.isContentEditable);
    if (typing) return;
    if (e.altKey && !e.ctrlKey && !e.metaKey && e.key.toLowerCase() === "d") {
      e.preventDefault();
      btn.click();
    }
  });
}

(function boot() {
  const shell = document.getElementById("z-shell");
  if (!shell) return;

  // Let diagnostics know the main bundle + selection ESM executed
  try {
    window.__pcIndexBooted = true;
    window.__pcESMLibraryReady = true;
    window.__pcSelectionESMReady = true;
  } catch {
    // ignore
  }

  // Left rail first (snappier)
  initGroups();
  initYearsWidget();

  // Core behaviors
  initSelection();
  initBulkDelete();
  initSearchAndPaging();
  initCollectionsAndContextMenus();
  initPanelsAndColumns();
  initDetailsPanel();
  initHoverPrefetch();

  // Diagnostics toggle in toolbar
  initDiagnosticsToggle();

  ensureInitialRows();
})();
