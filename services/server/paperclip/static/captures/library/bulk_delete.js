// services/server/paperclip/static/captures/library/bulk_delete.js
import { qsa, on, trigger, ROWS_CHANGED, SELECTION, toast } from "./dom.js";
import { post } from "./events.js"; // existing helper for POSTs

const UNDO_WINDOW_MS = 5000; // toast duration == delete flush window

export function initBulkDelete() {
  const btn = document.getElementById("pc-bulk-delete");
  if (!btn) return;

  on(btn, "click", () => {
    const selRows = qsa("tr[data-id].pc-row--selected");
    if (!selRows.length) return;

    const ids = selRows.map((tr) => tr.getAttribute("data-id")).filter(Boolean);
    if (!ids.length) return;

    // Mark pending in the UI
    selRows.forEach((tr) => tr.classList.add("pc-row--pending"));

    let canceled = false;

    function cancel() {
      canceled = true;
      // Restore rows
      selRows.forEach((tr) => tr.classList.remove("pc-row--pending"));
    }

    // When the toast disappears (either auto or manual dismiss), if not canceled, flush now.
    function flushNow() {
      if (canceled) return;
      post("/captures/bulk-delete/", { ids })
        .then(() => {
          // Remove rows from DOM
          selRows.forEach((tr) => tr.remove());
          trigger(document, ROWS_CHANGED);
          toast({
            message: `Deleted ${ids.length} item${ids.length > 1 ? "s" : ""}.`,
            duration: 2000,
          });
        })
        .catch(() => {
          // If something went wrong, clear pending and tell the user
          selRows.forEach((tr) => tr.classList.remove("pc-row--pending"));
          toast({ message: "Delete failed.", duration: 3000 });
        });
    }

    toast({
      message: `Deleting ${ids.length} item${ids.length > 1 ? "s" : ""} in ${Math.round(
        UNDO_WINDOW_MS / 1000
      )}s — Undo?`,
      actionText: "Undo",
      duration: UNDO_WINDOW_MS,
      onAction: cancel,
      onClose: () => {
        // Auto-close or user dismissed: if not undone, flush now
        flushNow();
      },
    });
  });

  // Selection changes control button state (canonical event)
  document.addEventListener(SELECTION, () => {
    const selCount = qsa("tr[data-id].pc-row--selected").length;
    if (selCount > 0) {
      btn.removeAttribute("disabled");
    } else {
      btn.setAttribute("disabled", "disabled");
    }
  });
}
