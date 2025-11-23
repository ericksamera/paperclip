// services/server/paperclip/static/captures/library/features/bulk_delete.js
// Bulk delete with a single toast + Undo; idempotent wiring.
//
// Behavior:
// - Button text shows current selection count.
// - Click → mark rows pending + show “Deleting in 5s — Undo?” toast.
// - If user clicks Undo, we just roll back the pending styling.
// - If the toast times out, POST /captures/bulk-delete/ and remove rows,
//   then emit a canonical ROWS_CHANGED event.

import { qsa, on, toast } from "../infra/dom.js";
import { EVENTS, onSelectionChange, emitRowsChanged } from "../infra/events.js";
import { postForm } from "../infra/http.js";

const UNDO_WINDOW_MS = 5000;

export function initBulkDelete() {
  if (window.__pcBulkDeleteWired) return; // prevent double-binding
  window.__pcBulkDeleteWired = true;

  const btn = document.getElementById("pc-bulk-delete");
  if (!btn) return;

  const selectedRows = () => qsa("#pc-body tr.pc-row[aria-selected='true'][data-id]");

  function setBtnState() {
    const n = selectedRows().length;
    btn.disabled = n === 0;
    btn.textContent = n ? `Delete (${n})` : "Delete selected";
  }

  // Keep the button in sync with selection + row changes
  onSelectionChange(setBtnState);
  document.addEventListener(EVENTS.ROWS_CHANGED, setBtnState, {
    capture: true,
  });
  setBtnState();

  // Only one visible toast per operation
  let activeToast = null;

  on(btn, "click", async () => {
    const rows = selectedRows();
    if (!rows.length) return;

    const ids = rows.map((r) => r.getAttribute("data-id")).filter(Boolean);
    if (!ids.length) return;

    // Mark pending in the UI (CSS grays + disables)
    rows.forEach((r) => {
      r.classList.add("pc-row--pending");
      r.setAttribute("aria-disabled", "true");
    });

    let canceled = false;
    const cancel = () => {
      canceled = true;
      rows.forEach((r) => {
        r.classList.remove("pc-row--pending");
        r.removeAttribute("aria-disabled");
      });
      setBtnState();
    };

    const flushNow = async () => {
      if (canceled) return;
      try {
        const entries = ids.map((id) => ["ids[]", id]);
        const resp = await postForm("/captures/bulk-delete/", entries);
        if (!resp) return; // redirect handled
        if (!resp.ok) throw new Error(String(resp.status));

        rows.forEach((r) => r.remove());
        emitRowsChanged({ reason: "bulk-delete", count: ids.length });

        toast({
          message: `Deleted ${ids.length} item${ids.length > 1 ? "s" : ""}.`,
        });
      } catch (err) {
        console.error("[bulk_delete] flush failed:", err);
        // Roll back UI on error
        cancel();
        toast({ message: "Delete failed.", duration: 3000 });
      } finally {
        activeToast = null;
      }
    };

    // Avoid duplicate toasts if something triggered twice
    if (activeToast) {
      return;
    }

    activeToast = toast({
      message: `Deleting ${ids.length} item${ids.length > 1 ? "s" : ""} in 5s — Undo?`,
      actionText: "Undo",
      duration: UNDO_WINDOW_MS,
      onAction: cancel,
      onClose: flushNow,
    });
  });
}
