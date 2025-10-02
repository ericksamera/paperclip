// captures/library/index.js
// Entry: wire up selection, search/paging, context menus, bulk delete, details panel,
// and panels/columns so column visibility & widths apply.

import "./events.js";

import { initSelection } from "./selection.js";
import { initBulkDelete } from "./bulk_delete.js";
import { initSearchAndPaging, ensureInitialRows } from "./search_paging.js";
import { initCollectionsAndContextMenus } from "./collections_ctx_dnd.js";
import { initDetailsPanel } from "./details_panel.js";
import { initPanelsAndColumns } from "./columns_panels.js";

(function boot() {
  if (!document.getElementById("z-shell")) return;

  initSelection();
  initBulkDelete();
  initSearchAndPaging();
  initCollectionsAndContextMenus();
  initPanelsAndColumns();
  initDetailsPanel();

  ensureInitialRows();

  document.dispatchEvent(new CustomEvent("pc:rows-updated"));
  document.dispatchEvent(new CustomEvent("pc:rows-changed"));
})();
