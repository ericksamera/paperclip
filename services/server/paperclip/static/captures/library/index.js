// services/server/paperclip/static/captures/library/index.js
// Single entry for Library UI: rows/selection, bulk actions, search/paging,
// collections + DnD + context menus, panels/columns, details panel, hover prefetch,
// collapsible left-rail groups, and the Years histogram widget.
//
// NOTE: CSS is linked in the template; do not import CSS from JS in plain-browser ESM.

import "./events.js";
import { initSelection } from "./selection.js";
import { initBulkDelete } from "./bulk_delete.js";
import { initSearchAndPaging, ensureInitialRows } from "./search_paging.js";
import { initCollectionsAndContextMenus } from "./collections_ctx_dnd.js";
import { initDetailsPanel } from "./details_panel.js";
import { initPanelsAndColumns } from "./columns_panels.js";
import { initHoverPrefetch } from "./hover_prefetch.js";
import { initGroups } from "./groups.js";
import { initYearsWidget } from "./years_hist.js";

(function boot() {
  const shell = document.getElementById("z-shell");
  if (!shell) return;

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
