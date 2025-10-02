// services/server/paperclip/static/captures/library/collections_ctx_dnd.js
// Drag & drop rows to Collections + row context menu (“Add to… / Remove from…”).
// Uses the centralized helpers in dom.js and the shared state bag in state.js.

import {
  $, $$, on, csrfToken, buildQs, toast,
  currentCollectionId, scanCollections, keepOnScreen
} from "./dom.js";
import { state } from "./state.js";

/* ───────────────────────── Helpers ───────────────────────── */

function tbody() {
  return (
    document.querySelector("#pc-body") ||
    document.querySelector(".pc-table tbody") ||
    document.querySelector("tbody")
  );
}

function selectedIds() {
  // selection.js mirrors its internal Set into window.PCState.selected,
  // and state.js exposes the same bag under `state`.
  return [...(state.selected || new Set())];
}

async function assignIdsToCollection(ids, colId, op /* "add" | "remove" */) {
  if (!ids?.length || !colId) return;
  const fd = new FormData();
  fd.append("csrfmiddlewaretoken", csrfToken());
  fd.append("op", op);
  ids.forEach(id => fd.append("ids", id));

  const resp = await fetch(`/collections/${colId}/assign/`, {
    method: "POST",
    body: fd,
    credentials: "same-origin",
    headers: { "X-CSRFToken": csrfToken() },
  });

  if (resp.redirected) { location.href = resp.url; return; }
  if (resp.ok) { location.reload(); return; }
  toast(`${op === "add" ? "Add to" : "Remove from"} collection failed (HTTP ${resp.status}).`);
}

/* ───────────────── Drag & drop: rows → Collections ───────────────── */

function ensureRowsDraggable() {
  const tb = tbody();
  if (!tb) return;
  tb.querySelectorAll("tr.pc-row").forEach(tr => {
    if (tr.getAttribute("draggable") !== "true") tr.setAttribute("draggable", "true");
  });
}

// Simple “N selected” ghost image
let ghostEl = null;
function makeGhost(count) {
  if (ghostEl) ghostEl.remove();
  const g = document.createElement("div");
  g.className = "pc-drag-ghost";
  g.textContent = `${count} selected`;
  document.body.appendChild(g);
  ghostEl = g;
  return g;
}

function wireRowDragEvents() {
  const tb = tbody();
  if (!tb) return;

  on(tb, "dragstart", (e) => {
    const tr = e.target.closest("tr.pc-row"); if (!tr) return;
    // If dragging an unselected row, select just that row
    if (tr.getAttribute("aria-selected") !== "true") {
      // Use selection.js behavior by simulating a click; keeps state in sync.
      tr.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    }
    const ids = selectedIds();
    e.dataTransfer.effectAllowed = "copyMove";
    const payload = JSON.stringify({ type: "pc-ids", ids });
    e.dataTransfer.setData("text/plain", payload);
    e.dataTransfer.setData("application/json", payload);
    const g = makeGhost(ids.length);
    try { e.dataTransfer.setDragImage(g, 10, 10); } catch {}
    document.body.classList.add("pc-dragging");
  });

  on(tb, "dragend", () => {
    document.body.classList.remove("pc-dragging");
    try { ghostEl?.remove(); } finally { ghostEl = null; }
  });
}

function addDndHandlersToCollectionAnchor(aEl, colId) {
  on(aEl, "dragenter", (e) => { e.preventDefault(); aEl.classList.add("dnd-over"); });
  on(aEl, "dragover",  (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
  on(aEl, "dragleave", () => aEl.classList.remove("dnd-over"));
  on(aEl, "drop", async (e) => {
    e.preventDefault(); e.stopPropagation();
    aEl.classList.remove("dnd-over");

    // Prefer payload; fall back to current selection for safety.
    let ids = selectedIds();
    try {
      const data = e.dataTransfer.getData("text/plain") || e.dataTransfer.getData("application/json");
      const obj = JSON.parse(data || "{}");
      if (obj?.type === "pc-ids" && Array.isArray(obj.ids) && obj.ids.length) ids = obj.ids;
    } catch {}
    if (ids.length) await assignIdsToCollection(ids, colId, "add");
  });
}

function wireCollectionsDnd() {
  // scanCollections() returns [{ id, label, el }] pointing at the <a> in the rail.
  scanCollections().forEach(({ el, id }) => addDndHandlersToCollectionAnchor(el, id));
}

/* ───────────────────── Row context menu ───────────────────── */

let menuEl = null;
let submenuAddEl = null;
let submenuRemoveEl = null;

function ensureRowMenuShell() {
  if (menuEl) return;
  menuEl = document.createElement("div");
  menuEl.className = "pc-context";
  document.body.appendChild(menuEl);

  submenuAddEl = document.createElement("div");
  submenuAddEl.className = "pc-submenu";
  submenuRemoveEl = document.createElement("div");
  submenuRemoveEl.className = "pc-submenu";
  document.body.appendChild(submenuAddEl);
  document.body.appendChild(submenuRemoveEl);
}

function submenuHtml(items) {
  return `<ul class="pc-menu">
    ${items.map(i => `<li class="pc-subitem" data-col="${i.id}">${i.label}</li>`).join("")}
  </ul>`;
}

function populateSubmenu(host, mode /* "add" | "remove" */) {
  const items = scanCollections();
  host.innerHTML = submenuHtml(items);
  host.style.display = "none";

  host.querySelectorAll(".pc-subitem").forEach(li => {
    li.addEventListener("click", async (e) => {
      e.preventDefault(); e.stopPropagation();
      const colId = li.getAttribute("data-col");
      const ids = selectedIds();
      if (ids.length && colId) await assignIdsToCollection(ids, colId, mode);
    }, { once: true });
  });
}

function openSubmenuFor(anchorLi) {
  const which = anchorLi?.dataset?.sub;
  const menuRect = menuEl.getBoundingClientRect();
  let host = null;
  if (which === "add")   host = submenuAddEl;
  if (which === "remove") host = submenuRemoveEl;
  if (!host) return;

  const r = anchorLi.getBoundingClientRect();
  host.style.display = "block";
  host.style.left = (menuRect.right - 2) + "px";
  host.style.top  = (r.top) + "px";
  keepOnScreen(host);
}

function hideSubmenus() {
  if (submenuAddEl) submenuAddEl.style.display = "none";
  if (submenuRemoveEl) submenuRemoveEl.style.display = "none";
}

function showRowMenu(x, y) {
  ensureRowMenuShell();

  const curCol = currentCollectionId(); // when filtered by a collection, show a direct “Remove from this collection”
  menuEl.innerHTML = `
    <ul class="pc-menu">
      <li data-act="open">Open</li>
      <li data-act="open-ext">Open DOI/URL</li>
      <li data-act="copy-doi">Copy DOI</li>
      <li class="sep"></li>
      <li class="has-sub" data-sub="add">Add to collection ▸</li>
      ${curCol
        ? `<li data-act="remove-here">Remove from this collection</li>`
        : `<li class="has-sub" data-sub="remove">Remove from collection ▸</li>`
      }
      <li class="sep"></li>
      <li class="danger" data-act="delete">Delete…</li>
    </ul>
  `;

  // Prepare submenus each time (collections list can change)
  populateSubmenu(submenuAddEl, "add");
  if (!curCol) populateSubmenu(submenuRemoveEl, "remove");

  menuEl.style.display = "block";
  menuEl.style.left = x + "px";
  menuEl.style.top  = y + "px";
  keepOnScreen(menuEl);

  // Hover to open submenus
  menuEl.querySelectorAll(".has-sub").forEach(li => {
    li.addEventListener("mouseenter", () => { hideSubmenus(); openSubmenuFor(li); });
  });

  // Click handlers
  menuEl.addEventListener("click", onRowMenuClick, { once: true });
  document.addEventListener("click", hideRowMenu, { capture: true, once: true });
  window.addEventListener("scroll", hideRowMenu, { capture: true, once: true });
  window.addEventListener("resize", hideRowMenu, { capture: true, once: true });
}

function hideRowMenu() {
  if (menuEl) menuEl.style.display = "none";
  hideSubmenus();
}

function findFirstRow() {
  return (tbody() || document).querySelector("tr.pc-row[aria-selected='true']") ||
         (tbody() || document).querySelector("tr.pc-row");
}

function onRowMenuClick(e) {
  const act = e.target?.dataset?.act;
  const tr = findFirstRow();
  if (!act || !tr) return;

  if (act === "open") {
    // Use the canonical details URL under /captures/<id>/ (works across templates).
    location.href = `/captures/${tr.dataset.id}/`;
  } else if (act === "open-ext") {
    const href = tr.dataset.doiUrl || tr.dataset.url;
    if (href) window.open(href, "_blank", "noopener");
  } else if (act === "copy-doi") {
    const doi = tr.dataset.doi;
    if (doi && navigator.clipboard?.writeText) navigator.clipboard.writeText(doi);
  } else if (act === "remove-here") {
    const curCol = currentCollectionId();
    if (curCol) assignIdsToCollection(selectedIds(), curCol, "remove");
  } else if (act === "delete") {
    // Defer to the existing bulk-delete handler (button lives in the toolbar module).
    $("#pc-bulk-delete")?.click();
  }
  hideRowMenu();
}

/* ───────────────────────── Bootstrapping ───────────────────────── */

export function initCollectionsAndContextMenus() {
  // 1) DnD
  ensureRowsDraggable();
  wireRowDragEvents();
  wireCollectionsDnd();

  // Re‑apply draggability whenever rows change (search, paging, etc.).
  document.addEventListener("pc:rows-changed", ensureRowsDraggable); // selection.js re‑emits this for legacy events too.

  // 2) Row context menu on right‑click
  const tb = tbody();
  if (tb) {
    on(tb, "contextmenu", (e) => {
      const tr = e.target.closest("tr.pc-row");
      if (!tr) return;
      e.preventDefault();

      // If right‑clicking an unselected row, select it alone so actions apply intuitively.
      if (tr.getAttribute("aria-selected") !== "true") {
        tr.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
      }
      showRowMenu(e.clientX, e.clientY);
    });
  }
}
