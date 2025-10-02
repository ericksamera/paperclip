// services/server/paperclip/static/captures/library/collections_ctx_dnd.js
import {
  $, $$, on, csrfToken, escapeHtml, toast,
  currentCollectionId, scanCollections, keepOnScreen
} from "./dom.js";
import { state } from "./state.js";

/* --------------------- Assign helpers --------------------- */
async function assignIdsToCollection(ids, colId, op) {
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

  if (resp.redirected) { window.location.href = resp.url; return; }
  if (resp.ok) { window.location.reload(); return; }
  alert(`${op === "add" ? "Add to" : "Remove from"} collection failed (${resp.status}).`);
}

function idsFromSelection() {
  return [...state.selected];
}

/* --------------------- DnD to Collections rail --------------------- */
function addDndHandlers(el, colId) {
  on(el, "dragenter", (e) => { e.preventDefault(); el.classList.add("dnd-over"); });
  on(el, "dragover",  (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
  on(el, "dragleave", () => { el.classList.remove("dnd-over"); });
  on(el, "drop", async (e) => {
    e.preventDefault(); e.stopPropagation();
    el.classList.remove("dnd-over");
    try {
      const data = e.dataTransfer.getData("text/plain") || e.dataTransfer.getData("application/json");
      let obj = {};
      try { obj = JSON.parse(data || "{}"); } catch {}
      const ids = (obj.type === "pc-ids" && Array.isArray(obj.ids) && obj.ids.length)
        ? obj.ids
        : idsFromSelection();
      if (ids.length) await assignIdsToCollection(ids, colId, "add");
    } catch (err) { console.warn(err); }
  });
}

function wireCollectionsDnd() {
  const cols = scanCollections();
  cols.forEach(({ el, id }) => addDndHandlers(el, id));
}

/* --------------------- Row context menu --------------------- */
let menuEl = null, submenuAddEl = null, submenuRemoveEl = null;

function ensureRowMenu() {
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

  on(menuEl, "mousemove", (e) => {
    const li = e.target.closest("[data-sub]");
    if (!li) { submenuAddEl.style.display = "none"; submenuRemoveEl.style.display = "none"; return; }
    const kind  = li.getAttribute("data-sub");
    const box   = menuEl.getBoundingClientRect();
    const liBox = li.getBoundingClientRect();
    const el    = (kind === "remove") ? submenuRemoveEl : submenuAddEl;
    const other = (kind === "remove") ? submenuAddEl : submenuRemoveEl;

    other.style.display = "none";
    el.style.display = "block";
    el.style.left = (box.right + 2) + "px";
    el.style.top  = liBox.top + "px";
    keepOnScreen(el);
  });

  on(menuEl, "mouseleave", () => {
    submenuAddEl.style.display = "none";
    submenuRemoveEl.style.display = "none";
  });

  on(menuEl, "click", onRowMenuClick);

  // Close on outside interactions
  ["click", "scroll", "resize"].forEach(ev =>
    on(window, ev, hideRowMenu, { passive: true })
  );
}

function populateSubmenu(el, op) {
  const cols = scanCollections();
  const html =
    cols.map(c =>
      `<div class="pc-subitem" data-col="${escapeHtml(c.id)}">${escapeHtml(c.label)}</div>`
    ).join("") || `<div class="pc-subitem disabled">(no collections)</div>`;
  el.innerHTML = html;

  on(el, "click", (e) => {
    const d = e.target.closest(".pc-subitem");
    if (!d || d.classList.contains("disabled")) return;
    const ids = idsFromSelection();
    assignIdsToCollection(ids, d.getAttribute("data-col"), op).catch(() => {});
    hideRowMenu();
  }, { once: true });
}

function onRowMenuClick(e) {
  const actEl = e.target.closest("[data-act]");
  if (!actEl) return;
  const act = actEl.getAttribute("data-act");

  if (act === "open") {
    const tr = document.querySelector("#pc-body tr.pc-row[aria-selected='true']") ||
               document.querySelector("#pc-body tr.pc-row");
    if (tr) window.location.href = `/captures/${tr.dataset.id}/`;
  } else if (act === "open-ext") {
    const tr = document.querySelector("#pc-body tr.pc-row[aria-selected='true']") ||
               document.querySelector("#pc-body tr.pc-row");
    if (tr) {
      const href = tr.dataset.doiUrl || tr.dataset.url;
      if (href) window.open(href, "_blank", "noopener");
    }
  } else if (act === "copy-doi") {
    const tr = document.querySelector("#pc-body tr.pc-row[aria-selected='true']");
    if (tr?.dataset?.doi) navigator.clipboard?.writeText(tr.dataset.doi);
  } else if (act === "remove-here") {
    const curCol = currentCollectionId();
    if (!curCol) return;
    const ids = idsFromSelection();
    assignIdsToCollection(ids, curCol, "remove");
  } else if (act === "delete") {
    document.getElementById("pc-bulk-delete")?.click();
  }
  hideRowMenu();
}

function hideRowMenu() {
  if (menuEl) menuEl.style.display = "none";
  if (submenuAddEl) submenuAddEl.style.display = "none";
  if (submenuRemoveEl) submenuRemoveEl.style.display = "none";
}

function showRowMenu(x, y) {
  ensureRowMenu();
  const curCol = currentCollectionId();
  menuEl.innerHTML = `
    <ul class="pc-menu">
      <li data-act="open">Open</li>
      <li data-act="open-ext">Open DOI/URL</li>
      <li data-act="copy-doi">Copy DOI</li>
      <li class="sep"></li>
      <li class="has-sub" data-sub="add">Add to collection ▸</li>
      ${curCol ? `<li data-act="remove-here">Remove from this collection</li>` : `<li class="has-sub" data-sub="remove">Remove from collection ▸</li>`}
      <li class="sep"></li>
      <li class="danger" data-act="delete">Delete…</li>
    </ul>
  `;
  menuEl.style.display = "block";
  menuEl.style.left = x + "px";
  menuEl.style.top  = y + "px";
  populateSubmenu(submenuAddEl, "add");
  if (!currentCollectionId()) { populateSubmenu(submenuRemoveEl, "remove"); } else { submenuRemoveEl.style.display = "none"; }
  keepOnScreen(menuEl);
}

/* --------------------- Init --------------------- */
export function initCollectionsAndContextMenus() {
  // Row right-click menu
  const tbody = document.getElementById("pc-body");
  on(tbody, "contextmenu", (e) => {
    const tr = e.target.closest("tr.pc-row");
    if (!tr) return;
    e.preventDefault();
    // If right-clicked row isn’t already selected, select it
    if (tr.getAttribute("aria-selected") !== "true") {
      document.querySelectorAll("#pc-body tr.pc-row[aria-selected='true']")
        .forEach(x => x.setAttribute("aria-selected", "false"));
      tr.setAttribute("aria-selected", "true");
      state.selected = new Set([tr.dataset.id]);
    }
    showRowMenu(e.pageX, e.pageY);
  });

  // Collections right-click menu is owned by legacy library.js; just delegate if present
  const zLeft = document.getElementById("z-left");
  on(zLeft, "contextmenu", (e) => {
    const link = e.target.closest(".z-link[data-collection-id]");
    if (!link) return;
    e.preventDefault();
    e.stopPropagation();
    // If legacy showColMenu exists, use it
    window.showColMenu?.(e.pageX, e.pageY, link);
  });

  // Wire DnD now and whenever rows/rail change
  wireCollectionsDnd();
  on(document, "pc:rows-updated", wireCollectionsDnd);
}
