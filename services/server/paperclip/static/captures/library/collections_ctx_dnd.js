// services/server/paperclip/static/captures/library/collections_ctx_dnd.js
// Drag & drop rows → Collections + row context menu (“Add/Remove…”)
// + Collections sidebar: “+ New”, right‑click (Open/Rename/Delete).
// Idempotent bindings; plays nicely with tbody swaps and other modules.

import {
  $, $$, on, csrfToken, toast, keepOnScreen,
  currentCollectionId, scanCollections
} from "./dom.js";
import { state } from "./state.js";

/* ───────────────────────── Tiny helpers ───────────────────────── */

function tbody() {
  return (
    document.querySelector("#pc-body") ||
    document.querySelector(".pc-table tbody") ||
    document.querySelector("tbody")
  );
}
function selectedIds() {
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
  const tb = tbody(); if (!tb) return;
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
  const tb = tbody(); if (!tb) return;

  on(tb, "dragstart", (e) => {
    const tr = e.target.closest("tr.pc-row"); if (!tr) return;
    // If dragging an unselected row, select just that row via the normal click path.
    if (tr.getAttribute("aria-selected") !== "true") {
      tr.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    }
    const ids = selectedIds();
    e.dataTransfer.effectAllowed = "copyMove";
    const payload = JSON.stringify({ type: "pc-ids", ids });
    e.dataTransfer.setData("text/plain", payload);
    e.dataTransfer.setData("application/json", payload);
    try { e.dataTransfer.setDragImage(makeGhost(ids.length), 10, 10); } catch {}
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
  scanCollections().forEach(({ el, id }) => addDndHandlersToCollectionAnchor(el, id));
}

/* ───────────────────── Row context menu ───────────────────── */

let rowMenuEl = null, submenuAddEl = null, submenuRemoveEl = null;

function ensureRowMenu() {
  if (rowMenuEl) return;
  rowMenuEl = document.createElement("div");
  rowMenuEl.className = "pc-context";
  document.body.appendChild(rowMenuEl);

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
function populateSubmenu(host, op /* "add" | "remove" */) {
  const items = scanCollections();
  host.innerHTML = submenuHtml(items);
  host.style.display = "none";
  host.querySelectorAll(".pc-subitem").forEach(li => {
    li.addEventListener("click", async (e) => {
      e.preventDefault(); e.stopPropagation();
      const colId = li.getAttribute("data-col");
      const ids = selectedIds();
      if (ids.length && colId) await assignIdsToCollection(ids, colId, op);
      hideRowMenu();
    }, { once: true });
  });
}
function openSubmenuFor(anchorLi) {
  const which = anchorLi?.dataset?.sub;
  const host = (which === "add") ? submenuAddEl : (which === "remove" ? submenuRemoveEl : null);
  if (!host) return;
  const rMenu = rowMenuEl.getBoundingClientRect();
  const r = anchorLi.getBoundingClientRect();
  host.style.display = "block";
  host.style.left = (rMenu.right - 2) + "px";
  host.style.top  = r.top + "px";
  keepOnScreen(host);
}
function hideSubmenus() {
  if (submenuAddEl)   submenuAddEl.style.display = "none";
  if (submenuRemoveEl) submenuRemoveEl.style.display = "none";
}
function hideRowMenu() {
  if (rowMenuEl) rowMenuEl.style.display = "none";
  hideSubmenus();
}
function firstSelectedOrAny() {
  return (tbody() || document).querySelector("tr.pc-row[aria-selected='true']") ||
         (tbody() || document).querySelector("tr.pc-row");
}
function onRowMenuClick(e) {
  const act = e.target?.closest?.("[data-act]")?.getAttribute("data-act");
  const tr  = firstSelectedOrAny();
  if (!act || !tr) return;

  if (act === "open") {
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
    document.getElementById("pc-bulk-delete")?.click();
  }
  hideRowMenu();
}
function showRowMenu(x, y) {
  ensureRowMenu();
  const curCol = currentCollectionId();
  rowMenuEl.innerHTML = `
    <ul class="pc-menu">
      <li data-act="open">Open</li>
      <li data-act="open-ext">Open DOI/URL</li>
      <li data-act="copy-doi">Copy DOI</li>
      <li class="sep"></li>
      <li class="has-sub" data-sub="add">Add to collection ▸</li>
      ${curCol ? `<li data-act="remove-here">Remove from this collection</li>`
               : `<li class="has-sub" data-sub="remove">Remove from collection ▸</li>`}
      <li class="sep"></li>
      <li class="danger" data-act="delete">Delete…</li>
    </ul>
  `;
  // Prepare submenus on each open (collections list can change)
  populateSubmenu(submenuAddEl, "add");
  if (!curCol) populateSubmenu(submenuRemoveEl, "remove");

  rowMenuEl.style.display = "block";
  rowMenuEl.style.left = x + "px";
  rowMenuEl.style.top  = y + "px";
  keepOnScreen(rowMenuEl);

  // Hover to open submenus
  rowMenuEl.querySelectorAll(".has-sub").forEach(li => {
    li.addEventListener("mouseenter", () => { hideSubmenus(); openSubmenuFor(li); });
  });

  // One‑shot close handlers
  rowMenuEl.addEventListener("click", onRowMenuClick, { once: true });
  document.addEventListener("click", hideRowMenu, { capture: true, once: true });
  window.addEventListener("scroll", hideRowMenu, { capture: true, once: true });
  window.addEventListener("resize", hideRowMenu, { capture: true, once: true });
}

/* ───────────── Collections sidebar: modal + right‑click ───────────── */

const modalEl     = document.getElementById("pc-modal");
const modalTitle  = document.getElementById("pc-modal-title");
const modalInput  = document.getElementById("pc-modal-input");
const modalCancel = document.getElementById("pc-modal-cancel");
const modalSubmit = document.getElementById("pc-modal-submit");

let modalHandler = null;
function openInputModal({ title, placeholder, initial, submitText, onSubmit }) {
  if (!modalEl) return; // template didn't include it
  modalTitle.textContent = title || "Input";
  modalInput.placeholder = placeholder || "";
  modalInput.value = initial || "";
  modalSubmit.textContent = submitText || "OK";
  modalHandler = onSubmit || null;

  // UX: disable primary until there’s a value; Enter submits
  function syncDisabled() { modalSubmit.disabled = !(modalInput.value.trim().length > 0); }
  modalInput.removeEventListener("input", syncDisabled);
  modalInput.addEventListener("input", syncDisabled);
  modalInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !modalSubmit.disabled) modalSubmit.click();
  });
  syncDisabled();

  modalEl.style.display = "flex";
  modalEl.setAttribute("aria-hidden", "false");
  setTimeout(() => modalInput?.focus(), 0);
}
function closeModal() {
  if (!modalEl) return;
  modalEl.style.display = "none";
  modalEl.setAttribute("aria-hidden", "true");
  modalHandler = null;
}
modalCancel?.addEventListener("click", closeModal);
modalEl?.addEventListener("click", (e) => { if (e.target === modalEl) closeModal(); });
window.addEventListener("keydown", (e) => { if (e.key === "Escape" && modalEl?.style.display === "flex") closeModal(); });
modalSubmit?.addEventListener("click", async () => {
  if (!modalHandler) { closeModal(); return; }
  const v = (modalInput.value || "").trim();
  const ok = await modalHandler(v);
  if (ok !== false) closeModal();
});

async function createCollection(name, parentId=null) {
  if (!name) return false;
  const fd = new FormData();
  fd.append("csrfmiddlewaretoken", csrfToken());
  fd.append("name", name);
  if (parentId) fd.append("parent", parentId);
  const resp = await fetch("/collections/create/", {
    method: "POST", body: fd, credentials: "same-origin",
    headers: { "X-CSRFToken": csrfToken() },
  });
  if (resp.redirected) { location.href = resp.url; return true; }
  if (resp.ok) { location.reload(); return true; }
  alert("Create failed (" + resp.status + ")."); return false;
}
async function renameCollection(id, name) {
  if (!id || !name) return false;
  const fd = new FormData();
  fd.append("csrfmiddlewaretoken", csrfToken());
  fd.append("name", name);
  const resp = await fetch(`/collections/${id}/rename/`, {
    method: "POST", body: fd, credentials: "same-origin",
    headers: { "X-CSRFToken": csrfToken() },
  });
  if (resp.redirected) { location.href = resp.url; return true; }
  if (resp.ok) { location.reload(); return true; }
  alert("Rename failed (" + resp.status + ")."); return false;
}
async function deleteCollection(id) {
  if (!id) return false;
  const fd = new FormData();
  fd.append("csrfmiddlewaretoken", csrfToken());
  const resp = await fetch(`/collections/${id}/delete/`, {
    method: "POST", body: fd, credentials: "same-origin",
    headers: { "X-CSRFToken": csrfToken() },
  });
  if (resp.redirected) { location.href = resp.url; return true; }
  if (resp.ok) { location.reload(); return true; }
  alert("Delete failed (" + resp.status + ")."); return false;
}

// “+” button → new collection dialog (idempotent)
let _wiredPlus = false;
function wireNewCollectionButton() {
  if (_wiredPlus) return;
  _wiredPlus = true;
  const btn = document.getElementById("pc-col-add-btn");
  btn?.addEventListener("click", () => {
    openInputModal({
      title: "New collection",
      placeholder: "Name",
      submitText: "Create",
      onSubmit: (val) => createCollection(val),
    });
  });
}

// Right‑click on Collections (Open/Rename/Delete)
let colMenuEl = null, colMenuTarget = null, _wiredLeft = false;
function ensureColMenu(){
  if (colMenuEl) return;
  colMenuEl = document.createElement('div');
  colMenuEl.className = 'pc-context';
  colMenuEl.innerHTML = `
    <ul class="pc-menu">
      <li data-act="open">Open</li>
      <li data-act="dashboard">Open dashboard</li>
      <li data-act="rename">Rename…</li>
      <li class="danger" data-act="delete">Delete…</li>
    </ul>
  `;
  document.body.appendChild(colMenuEl);
  colMenuEl.addEventListener('click', onColMenuClick);

  // Close on any outside click/scroll/resize
  window.addEventListener('click', (e) => { if (!colMenuEl.contains(e.target)) hideColMenu(); });
  window.addEventListener('scroll', hideColMenu, { passive: true });
  window.addEventListener('resize', hideColMenu);
}

function onColMenuClick(e){
  const a = colMenuTarget;
  if (!a) return hideColMenu();
  const id = a.getAttribute('data-collection-id');
  const label = (a.querySelector('.z-label')?.textContent || '').trim();
  const act = e.target.closest('[data-act]')?.getAttribute('data-act');
  if (!act) return;

  if (act === 'open') {
    window.location.href = a.href || a.getAttribute('href') || '#';
  } else if (act === 'dashboard') {
    if (id) window.location.href = `/collections/${encodeURIComponent(id)}/dashboard/`;
  } else if (act === 'rename') {
    openInputModal({
      title: 'Rename collection',
      initial: label,
      submitText: 'Save',
      onSubmit: (val) => renameCollection(id, val)
    });
  } else if (act === 'delete') {
    if (confirm(`Delete collection “${label}”? Items remain in All items.`)) {
      deleteCollection(id);
    }
  }
  hideColMenu();
}
function showColMenu(x, y, target) {
  ensureColMenu();
  colMenuTarget = target;
  colMenuEl.style.display = "block";
  colMenuEl.style.left = x + "px";
  colMenuEl.style.top  = y + "px";
  keepOnScreen(colMenuEl);
}
function hideColMenu() {
  if (colMenuEl) colMenuEl.style.display = "none";
  colMenuTarget = null;
}
function wireCollectionsRightClick() {
  if (_wiredLeft) return;
  _wiredLeft = true;
  const zLeft = document.getElementById("z-left");
  zLeft?.addEventListener("contextmenu", (e) => {
    const link = e.target.closest?.(".z-link[data-collection-id], [data-collection-id].z-link, [data-collection-id]");
    if (!link || !zLeft.contains(link)) return;
    e.preventDefault();
    e.stopPropagation(); // do not bubble to the global row context delegate
    showColMenu(e.pageX, e.pageY, link);
  });
}

/* ───────────────────────── Bootstrapping ───────────────────────── */

let _docContextMenuUnsub = null;

export function initCollectionsAndContextMenus() {
  // 1) DnD
  ensureRowsDraggable();
  wireRowDragEvents();
  wireCollectionsDnd();

  // Re‑apply to new tbody whenever rows change (search/paging/inf‑scroll/delete).
  document.addEventListener("pc:rows-changed", () => {
    ensureRowsDraggable();
    wireRowDragEvents();
  });

  // 2) Row context menu on right‑click — delegate to document so it survives tbody swaps.
  if (!_docContextMenuUnsub) {
    _docContextMenuUnsub = on(document, "contextmenu", (e) => {
      const tr = e.target?.closest?.("tr.pc-row");
      const tb = tbody();
      if (!tr || !tb || !tb.contains(tr)) return; // ignore non‑row right‑clicks (e.g., left rail)
      e.preventDefault();

      // If right‑clicking an unselected row, select it so actions apply intuitively.
      if (tr.getAttribute("aria-selected") !== "true") {
        tr.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
      }
      showRowMenu(e.clientX, e.clientY);
    });
  }

  // 3) Sidebar: “+” New + collection context menu
  wireNewCollectionButton();
  wireCollectionsRightClick();
}
