// selection_harden.js — makes row selection work no matter which template rendered the table.
// Safe to include alongside existing scripts: it only binds once and plays nice with your UI.

(function () {
  if (window.__pcSelectionHardened__) return;
  window.__pcSelectionHardened__ = true;

  function getTbody() {
    return document.getElementById("pc-body") || document.querySelector(".pc-table tbody") || null;
  }

  function rowId(tr) {
    if (!tr) return "";
    if (tr.dataset && tr.dataset.id) return tr.dataset.id.trim();

    const pk = tr.getAttribute("data-id") || tr.getAttribute("data-pk") || tr.getAttribute("data-uuid");
    if (pk && pk.trim()) { tr.dataset.id = pk.trim(); return tr.dataset.id; }

    const a = tr.querySelector('a[href^="/captures/"]');
    const href = a && a.getAttribute("href");
    if (href) {
      const m = href.match(/\/captures\/([0-9a-fA-F-]{8,})/);
      if (m) { tr.dataset.id = m[1]; return m[1]; }
    }
    return "";
  }

  function hydrateRows(root) {
    const tb = root || getTbody();
    if (!tb) return;
    tb.querySelectorAll("tr").forEach(tr => {
      if (!tr.classList.contains("pc-row")) tr.classList.add("pc-row");
      if (!tr.hasAttribute("aria-selected")) tr.setAttribute("aria-selected", "false");
      rowId(tr);
      if (!tr.hasAttribute("draggable")) tr.setAttribute("draggable", "true");
    });
  }

  function rows() {
    const tb = getTbody();
    return tb ? Array.from(tb.querySelectorAll("tr.pc-row")) : [];
  }

  function toggle(tr, on) {
    if (!tr) return;
    const next = (on === undefined) ? (tr.getAttribute("aria-selected") !== "true") : !!on;
    tr.setAttribute("aria-selected", next ? "true" : "false");
    tr.classList.toggle("selected", next); // legacy CSS compatibility
  }

  function clearAll() {
    rows().forEach(r => toggle(r, false));
  }

  function keepTextSelection(e) {
    const s = (window.getSelection && window.getSelection().toString()) || "";
    if (s && s.trim()) return true;
    return false;
  }

  function isInteractive(el) {
    return !!el.closest("a,button,input,textarea,select,summary,label,[contenteditable=''],[contenteditable='true']");
  }

  let lastIndex = null;

  function handleClick(e) {
    const tb = getTbody();
    if (!tb) return;
    const tr = e.target.closest("tr.pc-row");
    if (!tr || !tb.contains(tr)) return;
    if (isInteractive(e.target)) return;
    if (keepTextSelection(e)) return;

    const list = rows();
    if (e.shiftKey && lastIndex != null) {
      e.preventDefault();
      const i = list.indexOf(tr);
      const [a,b] = i < lastIndex ? [i, lastIndex] : [lastIndex, i];
      for (let k = a; k <= b; k++) toggle(list[k], true);
    } else if (e.metaKey || e.ctrlKey) {
      toggle(tr);
      lastIndex = list.indexOf(tr);
    } else {
      clearAll();
      toggle(tr, true);
      lastIndex = list.indexOf(tr);
    }
    document.dispatchEvent(new CustomEvent("pc:rows-updated"));
  }

  function handleMouseDown(e) {
    const tb = getTbody(); if (!tb) return;
    const tr = e.target.closest("tr.pc-row"); if (!tr || !tb.contains(tr)) return;
    lastIndex = rows().indexOf(tr);
  }

  function handleContextMenu(e) {
    const tb = getTbody(); if (!tb) return;
    const tr = e.target.closest("tr.pc-row"); if (!tr || !tb.contains(tr)) return;
    // If right-clicking a non-selected row, select only it (don’t block any existing menu code).
    if (tr.getAttribute("aria-selected") !== "true") {
      clearAll();
      toggle(tr, true);
      document.dispatchEvent(new CustomEvent("pc:rows-updated"));
    }
  }

  // Optional: Delete/Backspace shortcut if your main script didn’t attach yet.
  function handleKeydown(e) {
    const tag = (e.target && (e.target.tagName || "")).toLowerCase();
    const typing = tag === "input" || tag === "textarea" || e.target.isContentEditable;
    if (typing) return;

    if ((e.key === "Delete" || e.key === "Backspace")) {
      const ids = rows().filter(r => r.getAttribute("aria-selected") === "true").map(r => rowId(r)).filter(Boolean);
      if (!ids.length) return;
      e.preventDefault();
      const btn = document.getElementById("pc-bulk-delete");
      if (btn) { btn.click(); return; }  // let your existing bulk_delete.js drive the POST
      // ultra-fallback: try posting the form directly
      const form = document.getElementById("pc-bulk-form");
      if (form && form.action) {
        const fd = new FormData();
        const csrf = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (csrf) fd.append("csrfmiddlewaretoken", csrf.value);
        ids.forEach(id => fd.append("ids", id));
        fetch(form.action, { method: "POST", body: fd, credentials: "same-origin" }).then(() => location.reload());
      }
    }
  }

  // Rehydrate any time the table body is swapped by Ajax/template
  const mo = new MutationObserver(() => hydrateRows());
  if (document.body) mo.observe(document.body, { childList: true, subtree: true });

  // First run
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { hydrateRows(); }, { once: true });
  } else {
    hydrateRows();
  }

  // Global (delegated) listeners — robust to tbody replacements
  document.addEventListener("click", handleClick, true);
  document.addEventListener("mousedown", handleMouseDown, true);
  document.addEventListener("contextmenu", handleContextMenu, true);
  window.addEventListener("keydown", handleKeydown, { capture: true });
})();
