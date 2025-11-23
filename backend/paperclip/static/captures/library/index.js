// backend/paperclip/static/captures/library/index.js
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

(function boot() {
  const shell = document.getElementById("z-shell");
  if (!shell) return;

  // Let diagnostics know the main bundle + selection ESM executed
  try {
    window.__pcIndexBooted = true;
    window.__pcESMLibraryReady = true;
    // This flag is what diagnostics.js looks for when it says
    // “selection.js loaded”.
    window.__pcSelectionESMReady = true;
  } catch {
    // ignore if window is locked down
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

  ensureInitialRows();
})();
