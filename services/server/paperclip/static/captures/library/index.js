// Entry point: wire up all modules for the Library page.
import { initSelection } from "./selection.js";
import { initBulkDelete } from "./bulk_delete.js";
import { initSearchAndPaging, ensureInitialRows } from "./search_paging.js";
import { initPanelsAndColumns } from "./columns_panels.js";
import { initCollectionsAndContextMenus } from "./collections_ctx_dnd.js";

(function boot() {
  if (!document.getElementById("z-shell")) return;

  initSelection();
  initBulkDelete();
  initPanelsAndColumns();
  initSearchAndPaging();
  initCollectionsAndContextMenus();
  ensureInitialRows(); // safe no-op if rows are already server-rendered

  document.dispatchEvent(new CustomEvent("pc:rows-updated"));
})();
