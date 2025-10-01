import { $, csrfToken, toast } from "./dom.js";
import { state } from "./state.js";

export function initBulkDelete() {
  const bulkForm = $("#pc-bulk-form");
  const bulkBtn  = $("#pc-bulk-delete");
  if (!bulkForm || !bulkBtn) return;

  // Only flush on unload if it wasn't canceled.
  window.addEventListener("beforeunload", () => {
    const pd = state.pendingDelete;
    if (pd && !pd.sent && !pd.canceled) {
      try { pd.flushNow?.(); } catch (_) {}
    }
  });

  bulkBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!state.selected.size) return;

    // If there’s a previous batch:
    // - if it was NOT canceled and NOT sent yet -> flush it first
    // - otherwise drop it
    if (state.pendingDelete) {
      const pd = state.pendingDelete;
      try {
        if (!pd.sent && !pd.canceled) {
          await pd.flushNow();
        }
      } catch (_) { /* ignore */ }
      state.pendingDelete = null;
    }

    const ids = Array.from(state.selected);
    const tbody = document.getElementById("pc-body");
    const rows = ids.map(id =>
      tbody.querySelector(`tr.pc-row[data-id="${CSS.escape(id)}"]`)
    ).filter(Boolean);

    // Optimistic UI
    rows.forEach(tr => { tr.classList.add("pc-row--pending"); tr.setAttribute("aria-selected", "false"); });
    state.selected.clear();
    updateBulkBtn(bulkBtn);

    let timer = null;
    let sent = false;
    let canceled = false;

    const flushNow = async () => {
      if (sent || canceled) return;
      sent = true;
      try {
        const fd = new FormData();
        fd.append("csrfmiddlewaretoken", csrfToken());
        ids.forEach(id => fd.append("ids", id));
        const resp = await fetch(bulkForm.action, {
          method: "POST",
          body: fd,
          credentials: "same-origin",
          headers: { "X-CSRFToken": csrfToken() }
        });
        if (resp.redirected) { window.location.href = resp.url; return; }
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        rows.forEach(tr => tr.remove());
        toast?.("Deleted " + ids.length + " item(s).", { duration: 2500 });
        document.dispatchEvent(new CustomEvent("pc:rows-updated"));
      } catch (err) {
        // Roll back on error
        rows.forEach(tr => tr.classList.remove("pc-row--pending"));
        toast?.("Delete failed. " + String(err), { duration: 4000 });
      }
    };

    // Proper UNDO: cancel the pending batch, restore UI, and clear pendingDelete.
    const cancel = () => {
      if (sent || canceled) return;
      canceled = true;
      try { clearTimeout(timer); } catch(_) {}
      // Roll back the UI
      rows.forEach(tr => tr.classList.remove("pc-row--pending"));
      rows.forEach(tr => { tr.setAttribute("aria-selected", "true"); state.selected.add(tr.dataset.id); });
      updateBulkBtn(bulkBtn);
      state.pendingDelete = null; // <— critical: don’t flush this later
    };

    toast?.(`Deleted ${ids.length} item(s) — Undo`, {
      actionText: "Undo",
      duration: 5000,
      onAction: cancel,
    });

    timer = setTimeout(() => { if (!canceled) flushNow(); }, 5000);
    state.pendingDelete = { ids, flushNow, sent, canceled, cancel };
  });
}

function updateBulkBtn(bulkBtn) {
  bulkBtn.disabled = state.selected.size === 0;
  bulkBtn.textContent = state.selected.size
    ? `Delete (${state.selected.size})`
    : "Delete selected";
}
