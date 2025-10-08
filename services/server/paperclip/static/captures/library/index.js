// services/server/paperclip/static/captures/library/index.js
// Single entry for Library UI: rows/selection, bulk actions, search/paging,
// collections + DnD + context menus, panels/columns, details panel, hover prefetch,
// and collapsible left-rail groups.

import "./events.js";
import { initSelection } from "./selection.js";
import { initBulkDelete } from "./bulk_delete.js";
import { initSearchAndPaging, ensureInitialRows } from "./search_paging.js";
import { initCollectionsAndContextMenus } from "./collections_ctx_dnd.js";
import { initDetailsPanel } from "./details_panel.js";
import { initPanelsAndColumns } from "./columns_panels.js";
import { initHoverPrefetch } from "./hover_prefetch.js";
import { initGroups } from "./groups.js";

(function boot() {
  const shell = document.getElementById("z-shell");
  if (!shell) return;

  // Left rail: wire collapsible groups first so it feels snappy on load.
  initGroups();

  // Core behaviors
  initSelection();
  initBulkDelete();
  initSearchAndPaging();
  initCollectionsAndContextMenus(); // dnd + context menus
  initPanelsAndColumns();           // column prefs + splitters
  initDetailsPanel();
  initHoverPrefetch();

  // Ensure first batch of rows is hydrated for keyboard/selection after initial render.
  ensureInitialRows();
})();
