/**
 * selection_harden.js — robust legacy binder (click + j/k + arrows)
 * Idempotent, and bails out if the ESM selection is active.
 */
(() => {
  // Bail if modern ESM selection has initialized
  if (window.__pcESMSelectionReady) {
    try { console.info("[paperclip] selection_harden skipped (ESM active)"); } catch {}
    return;
  }
  if (window.__pcLegacySelBound) return;
  window.__pcLegacySelBound = true;

  function isEditable(el) {
    if (!el) return false;
    if (el.isContentEditable) return true;
    const t = el.tagName;
    return t === "INPUT" || t === "TEXTAREA" || t === "SELECT";
  }
  function tbody() {
    return (
      document.querySelector("#z-table tbody") ||
      document.getElementById("pc-body") ||
      document.querySelector(".pc-table tbody") ||
      document.querySelector("tbody")
    );
  }
  function rows() {
    const tb = tbody();
    return tb ? Array.from(tb.querySelectorAll("tr.pc-row, tr[data-row='pc-row'], tr")) : [];
  }
  function current() {
    return document.querySelector(
      "tr.pc-row.is-selected, tr.pc-row.selected, tr.pc-row[aria-selected='true'], tr[data-selected='true']"
    );
  }

  function simulateClick(tr) {
    if (!tr) return;
    const ev = new MouseEvent("click", { bubbles: true, cancelable: true, view: window });
    // 🔒 mark as simulated so our capture listener can ignore (prevents recursion)
    Object.defineProperty(ev, "__pcSimulated", { value: true });
    tr.dispatchEvent(ev);

    // If no listener set selection, provide minimal UX fallback
    if (
      !tr.classList.contains("is-selected") &&
      !tr.classList.contains("selected") &&
      tr.getAttribute("aria-selected") !== "true"
    ) {
      tr.classList.add("selected");
      tr.setAttribute("aria-selected", "true");
    }
  }

  function move(delta) {
    const list = rows();
    if (!list.length) return;
    const cur = current();
    let idx = cur ? list.indexOf(cur) : -1;
    let next = idx >= 0 ? idx + delta : (delta > 0 ? 0 : list.length - 1);
    next = Math.max(0, Math.min(list.length - 1, next));
    const tr = list[next];
    try { tr.scrollIntoView({ block: "nearest" }); } catch {}
    simulateClick(tr);
    tr.setAttribute("tabindex", "-1");
    try { tr.focus({ preventScroll: true }); } catch {}
  }

  function onKeydown(e) {
    if (e.defaultPrevented) return;
    if (isEditable(e.target) || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); move(+1); }
    else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
  }

  function onClick(e) {
    // 🔒 ignore our own synthetic click
    if (e && e.__pcSimulated) return;

    const tb = tbody();
    if (!tb) return;

    const tr = e.target && e.target.closest && e.target.closest("tr");
    if (!tr || !tb.contains(tr)) return;
    if (isEditable(e.target)) return;

    // Let selection owner decide; we only simulate if needed
    simulateClick(tr);
  }

  document.addEventListener("keydown", onKeydown, true);
  document.addEventListener("click", onClick, true);
  try { console.info("[paperclip] selection_harden bound (legacy binder active)."); } catch {}
})();
