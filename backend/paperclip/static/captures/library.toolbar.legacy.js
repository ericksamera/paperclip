// services/server/paperclip/static/captures/library.toolbar.js
// Three things:
// 1) Restore 3-pane sizing from saved widths.
// 2) Replace “Download views” + “Export CSV” with one “Export ▾” dropdown.
// 3) DO NOT remove Delete/collections controls anymore (keep bulk delete working).

(function () {
  function qs(sel, root = document) { return root.querySelector(sel); }
  function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

  function leftWidth()  { return parseInt(localStorage.getItem("pc-left-w")  || "260", 10) || 260; }
  function rightWidth() { return parseInt(localStorage.getItem("pc-right-w") || "360", 10) || 360; }

  // Use canonical helper to avoid drift
  function currentCollectionId() {
    try { return window.PCDOM?.currentCollectionId?.() || "all"; }
    catch (_) { return "all"; }
  }

  function makeExportMenu() {
    // Reuse existing floating menu styles (.pc-context / .pc-menu)
    const menu = document.createElement("div");
    menu.className = "pc-context";
    menu.style.minWidth = "220px";
    menu.style.display = "none";
    menu.innerHTML = `
      <ul class="pc-menu" style="margin:6px 0; padding:4px 0">
        <li data-act="csv">Export CSV</li>
        <li data-act="views">Download views (.zip)</li>
      </ul>
    `;
    document.body.appendChild(menu);

    function openAt(x, y) {
      // compute hrefs each time in case col changes
      const col = currentCollectionId();
      menu.dataset.csvHref   = "/captures/export/";
      menu.dataset.viewsHref = "/collections/" + encodeURIComponent(col) + "/download-views.zip";

      menu.style.display = "block";
      menu.style.left = x + "px";
      menu.style.top  = y + "px";

      // Keep on screen via canonical helper
      try { window.PCDOM?.keepOnScreen?.(menu); } catch (_) {}
    }
    function close() { menu.style.display = "none"; }

    menu.addEventListener("click", (e) => {
      const li = e.target.closest("[data-act]");
      if (!li) return;
      if (li.dataset.act === "csv")   location.href = menu.dataset.csvHref;
      if (li.dataset.act === "views") location.href = menu.dataset.viewsHref;
      close();
    });

    // Close on outside click / escape / scroll / resize
    window.addEventListener("click", (e) => { if (!menu.contains(e.target) && e.target !== menu.anchorBtn) close(); });
    window.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    window.addEventListener("scroll", close, { passive: true });
    window.addEventListener("resize", close);

    return { el: menu, openAt, close };
  }

  function injectExportButton(toolbar) {
    const actions = qs(".z-actions", toolbar) || toolbar;

    // Hide the old "Download views" and "Export CSV" buttons if present
    qsa("a,button", actions).forEach((el) => {
      const txt = (el.textContent || "").trim().toLowerCase();
      if (txt === "download views" || txt === "export csv") {
        if (el && el.parentNode) el.parentNode.removeChild(el);
      }
    });

    // Create the single Export ▾ button
    const btn = document.createElement("button");
    btn.id = "pc-export";
    btn.className = "btn";
    btn.type = "button";
    btn.style.position = "relative";
    btn.textContent = "Export ▾";

    // Build the dropdown (reusing context menu styles)
    const menu = makeExportMenu();
    menu.el.anchorBtn = btn;

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const r = btn.getBoundingClientRect();
      menu.openAt(r.left, r.bottom + 4);
    });

    // Insert near the other actions
    const pivot =
      qs("#pc-cols-toggle", actions) ||
      qs("#z-toggle-right", actions) ||
      qs("#z-toggle-left", actions) ||
      null;
    if (pivot && pivot.parentNode === actions) {
      actions.insertBefore(btn, pivot);
    } else {
      actions.appendChild(btn);
    }
  }

  function boot() {
    const shell = document.getElementById("z-shell");
    if (!shell) return;

    // Respect saved widths and ensure left pane starts open
    shell.style.setProperty("--left-w",  leftWidth()  + "px");
    shell.style.setProperty("--right-w", rightWidth() + "px");
    localStorage.setItem("pc-left-hidden", "0");

    // Toolbar: keep Delete/Assign controls intact; just add Export menu
    const toolbar = qs(".z-toolbar");
    if (toolbar) injectExportButton(toolbar);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
