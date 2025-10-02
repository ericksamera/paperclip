// services/server/paperclip/static/captures/selection_harden.js
// Legacy safety binder: only active if the modern ESM selection isn't present.
// If ESM selection becomes ready later, we unbind ourselves.

(function () {
  // If ESM selection already signaled readiness, do nothing.
  if (window.__pcSelectionESM) {
    try { console.info("[paperclip] legacy selection: disabled (ESM present)."); } catch {}
    return;
  }

  let _bound = false;
  let _onKeydown = null;
  let _onClick = null;

  function isEditable(el) {
    if (!el) return false;
    const t = (el.tagName || "").toLowerCase();
    return (
      t === "input" || t === "textarea" || el.isContentEditable || t === "select"
    );
  }

  function tbody() { return document.querySelector("#pc-body"); }
  function rows() { return Array.from(document.querySelectorAll("#pc-body tr.pc-row")); }
  function current() { return document.querySelector("#pc-body tr.pc-row[aria-selected='true']"); }

  function simulateClick(tr) {
    if (!tr) return;
    try {
      tr.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    } catch {}
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

  function bind() {
    if (_bound) return;
    _onKeydown = (e) => {
      if (e.defaultPrevented) return;
      if (isEditable(e.target) || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); move(+1); }
      else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    };
    _onClick = (e) => {
      const tb = tbody();
      if (!tb) return;
      const tr = e.target && e.target.closest && e.target.closest("tr");
      if (!tr || !tb.contains(tr)) return;
      if (isEditable(e.target)) return;
      // Avoid fighting with native link clicks inside the row; let default happen then re-select
      simulateClick(tr);
    };
    document.addEventListener("keydown", _onKeydown, true);
    document.addEventListener("click", _onClick, true);
    _bound = true;
    try { console.info("[paperclip] legacy selection: bound."); } catch {}
  }

  function unbind() {
    if (!_bound) return;
    document.removeEventListener("keydown", _onKeydown, true);
    document.removeEventListener("click", _onClick, true);
    _onKeydown = _onClick = null;
    _bound = false;
    try { console.info("[paperclip] legacy selection: unbound (ESM took over)."); } catch {}
  }

  // If/when the ESM selection initializes, unbind ourselves.
  window.addEventListener("pc:selection-esm-ready", unbind, { once: true });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind, { once: true });
  } else {
    bind();
  }
})();
