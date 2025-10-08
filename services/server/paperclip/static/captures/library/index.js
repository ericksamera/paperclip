// services/server/paperclip/static/captures/library/index.js
// Single entry for Library UI: rows/selection, toolbar/panels, details panel,
// search + infinite scroll, context menus, bulk delete, and hover prefetch.

import "./events.js";
import { initSelection } from "./selection.js";
import { initBulkDelete } from "./bulk_delete.js";
import { initSearchAndPaging, ensureInitialRows } from "./search_paging.js";
import { initCollectionsAndContextMenus } from "./collections_ctx_dnd.js";
import { initDetailsPanel } from "./details_panel.js";
import { initPanelsAndColumns } from "./columns_panels.js";
import { initHoverPrefetch } from "./hover_prefetch.js";

(function boot() {
  if (!document.getElementById("z-shell")) return;

  initSelection();
  initBulkDelete();
  initSearchAndPaging();
  initCollectionsAndContextMenus();
  initPanelsAndColumns();
  initDetailsPanel();
  initHoverPrefetch();
  ensureInitialRows();
})();
