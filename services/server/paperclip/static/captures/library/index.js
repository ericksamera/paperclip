// services/server/paperclip/static/captures/library/index.js
// Entry: wire up events bridge, selection, paging, context menus, bulk delete,
// details panel, and panels/columns.

import "./events.js"; // ← make sure legacy events are bridged before anything else

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

  ensureInitialRows(); // if tbody shipped empty, load first page
})();
