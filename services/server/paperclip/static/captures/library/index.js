// captures/library/index.js
// Entry: wire up selection, search/paging, context menus, bulk delete, and the details panel.

import { initSelection } from "./selection.js";
import { initBulkDelete } from "./bulk_delete.js";
import { initSearchAndPaging, ensureInitialRows } from "./search_paging.js";
import { initCollectionsAndContextMenus } from "./collections_ctx_dnd.js";
import { initDetailsPanel } from "./details_panel.js";

(function boot() {
  if (!document.getElementById("z-shell")) return;

  initSelection();
  initBulkDelete();
  initSearchAndPaging();
  initCollectionsAndContextMenus();
  initDetailsPanel();

  // If the tbody shipped empty, load the first page.
  ensureInitialRows();

  // Nudge any legacy listeners.
  document.dispatchEvent(new CustomEvent("pc:rows-updated"));
})();
