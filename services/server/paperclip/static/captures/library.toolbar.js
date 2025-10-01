// services/server/paperclip/static/captures/library.toolbar.js
// Three things:
// 1) Restore 3-pane sizing from saved widths.
// 2) Replace “Download views” + “Export CSV” with one “Export ▾” dropdown.
// 3) Remove Delete/collections controls from the toolbar.
//
// No template changes needed.

(function () {
  function qs(sel, root = document) { return root.querySelector(sel); }
  function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }
  function hide(el) { if (el) el.style.display = "none"; }
  function remove(el) { if (el && el.parentNode) el.parentNode.removeChild(el); }

  function leftWidth()  { return parseInt(localStorage.getItem("pc-left-w")  || "260", 10) || 260; }
  function rightWidth() { return parseInt(localStorage.getItem("pc-right-w") || "360", 10) || 360; }

  function currentCollectionId() {
    try {
      const u = new URL(location.href);
      return (u.searchParams.get("col") || "").trim() || "all";
    } catch (_) {
      return "all";
    }
  }

  function makeExportMenu() {
    // Reuse existing floating menu styles (.pc-context / .pc-menu) from libraries.css
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
      menu.dataset.viewsHref = "/collections/" + encodeURIComponent(col) + "/download-views/";

      menu.style.display = "block";
      menu.style.left = x + "px";
      menu.style.top  = y + "px";

      // keep on screen
      const r = menu.getBoundingClientRect();
      let nx = r.left, ny = r.top, changed = false;
      if (r.right > innerWidth)  { nx = Math.max(8, innerWidth  - r.width  - 8); changed = true; }
      if (r.bottom > innerHeight) { ny = Math.max(8, innerHeight - r.height - 8); changed = true; }
      if (changed) { menu.style.left = nx + "px"; menu.style.top = ny + "px"; }
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
      if (txt === "download views" || txt === "export csv") remove(el);
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

    // Insert the button near the other actions (before Columns/Sidebar/Info if possible)
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

  function stripDangerousStuff(toolbar) {
    // Remove Delete selected (button + form) and collection assign strip
    const bulkBtn  = qs("#pc-bulk-delete", toolbar) || qs("#pc-bulk-delete");
    const bulkForm = qs("#pc-bulk-form", toolbar)   || qs("#pc-bulk-form");
    const sel      = qs("#pc-assign-select", toolbar) || qs("#pc-assign-select");
    const addBtn   = qs("#pc-assign-add", toolbar)    || qs("#pc-assign-add");
    const rmBtn    = qs("#pc-assign-remove", toolbar) || qs("#pc-assign-remove");

    // Remove from DOM so context menu “Delete…” becomes a no-op.
    remove(bulkBtn);
    remove(bulkForm);
    remove(addBtn);
    remove(rmBtn);
    remove(sel);
  }

  function boot() {
    const shell = document.getElementById("z-shell");
    if (!shell) return;

    // 1) Respect saved widths and ensure left pane starts open
    shell.style.setProperty("--left-w",  leftWidth()  + "px");
    shell.style.setProperty("--right-w", rightWidth() + "px");
    localStorage.setItem("pc-left-hidden", "0");

    // 2) Toolbar cleanup / export menu
    const toolbar = qs(".z-toolbar");
    if (toolbar) {
      stripDangerousStuff(toolbar);
      injectExportButton(toolbar);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
