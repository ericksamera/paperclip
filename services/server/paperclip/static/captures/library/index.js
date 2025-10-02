// captures/library/index.js
// Entry: wire up selection, search/paging, context menus, bulk delete, the details panel,
// and (NEW) panels/columns so column visibility & widths apply (DOI hidden by default).

import { initSelection } from "./selection.js";
import { initBulkDelete } from "./bulk_delete.js";
import { initSearchAndPaging, ensureInitialRows } from "./search_paging.js";
import { initCollectionsAndContextMenus } from "./collections_ctx_dnd.js";
import { initDetailsPanel } from "./details_panel.js";
import { initPanelsAndColumns } from "./columns_panels.js"; // NEW

(function boot() {
  if (!document.getElementById("z-shell")) return;

  initSelection();
  initBulkDelete();
  initSearchAndPaging();
  initCollectionsAndContextMenus();
  initDetailsPanel();
  initPanelsAndColumns(); // NEW: applies DEFAULT_COLS (doi:false) + wires the Columns editor

  // If the tbody shipped empty, load the first page.
  ensureInitialRows();

  // Nudge any listeners (legacy & new)
  document.dispatchEvent(new CustomEvent("pc:rows-updated"));
  document.dispatchEvent(new CustomEvent("pc:rows-changed"));
})();
