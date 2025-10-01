// captures/library/bulk_delete.js  (ESM)
import { $, csrfToken, toast } from "./dom.js";

function selectedRowEls() {
  return Array.from(document.querySelectorAll("#pc-body tr.pc-row[aria-selected='true']"));
}

function updateBulkBtnState(btn) {
  const n = selectedRowEls().length;
  if (!btn) return;
  btn.disabled = n === 0;
  btn.textContent = n ? `Delete (${n})` : "Delete selected";
}

export function initBulkDelete() {
  const bulkForm = $("#pc-bulk-form");
  const bulkBtn  = $("#pc-bulk-delete");
  if (!bulkForm || !bulkBtn) return;

  // Keep button label right if some other code toggles selection
  document.addEventListener("pc:rows-updated", () => updateBulkBtnState(bulkBtn));
  updateBulkBtnState(bulkBtn);

  // Flush any uncanceled pending delete if the user navigates away
  window.addEventListener("beforeunload", () => {
    const pd = window.PCState?.pendingDelete;
    if (pd && !pd.sent && !pd.canceled) {
      try { pd.flushNow?.(); } catch {}
    }
  });

  bulkBtn.addEventListener("click", async (e) => {
    e.preventDefault();

    const rows = selectedRowEls();
    if (!rows.length) return;

    // If there’s an older batch still pending and not canceled, flush it first
    if (window.PCState?.pendingDelete) {
      const pd = window.PCState.pendingDelete;
      try { if (!pd.sent && !pd.canceled) await pd.flushNow(); } catch {}
      window.PCState.pendingDelete = null;
    }

    const ids = rows.map(tr => tr.dataset.id).filter(Boolean);

    // Optimistic UI
    rows.forEach(tr => { tr.classList.add("pc-row--pending"); tr.setAttribute("aria-selected", "false"); });
    updateBulkBtnState(bulkBtn);

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
        if (resp.redirected) { location.href = resp.url; return; }
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        rows.forEach(tr => tr.remove());
        toast(`Deleted ${ids.length} item(s).`, { duration: 2500 });
        document.dispatchEvent(new CustomEvent("pc:rows-updated"));
      } catch (err) {
        // Roll back on error
        rows.forEach(tr => tr.classList.remove("pc-row--pending"));
        toast(`Delete failed. ${String(err)}`, { duration: 4000 });
      }
    };

    const cancel = () => {
      if (sent || canceled) return;
      canceled = true;
      try { clearTimeout(timer); } catch {}
      rows.forEach(tr => tr.classList.remove("pc-row--pending"));
      rows.forEach(tr => tr.setAttribute("aria-selected", "true"));
      updateBulkBtnState(bulkBtn);
      window.PCState && (window.PCState.pendingDelete = null);
    };

    toast(`Deleted ${ids.length} item(s) — Undo`, {
      actionText: "Undo",
      duration: 5000,
      onAction: cancel,
    });

    timer = setTimeout(() => { if (!canceled) flushNow(); }, 5000);
    window.PCState && (window.PCState.pendingDelete = { ids, flushNow, sent, canceled, cancel });
  });

  // Optional: when some other code toggles selection, keep the button accurate
  document.addEventListener("click", () => updateBulkBtnState(bulkBtn), { capture: true });
}

// Auto-boot when the page is ready
document.addEventListener("DOMContentLoaded", initBulkDelete);
