// services/server/paperclip/static/captures/library/collections_ctx_dnd.js
import { $, $$, on, csrfToken, escapeHtml, buildQs, toast } from "./dom.js";
import { state } from "./state.js";

// --- Helpers ---
function currentCollectionId() {
  const p = new URL(location.href).searchParams;
  return (p.get("col") || "").trim();
}
function scanCollections() {
  const zLeft = document.getElementById("z-left");
  if (!zLeft) return [];
  const links = [...zLeft.querySelectorAll("[data-collection-id], a[href*='col='], a[href^='/collections/']")];
  const list = [];
  links.forEach(a => {
    let id = a.getAttribute("data-collection-id");
    if (!id) {
      try {
        const href = a.getAttribute("href") || "";
        if (href.includes("col=")) {
          const u = new URL(href, location.href);
          id = u.searchParams.get("col");
        } else {
          const m = href.match(/\/collections\/([^/?#]+)/);
          if (m) id = m[1];
        }
      } catch(_) {}
    }
    const label = (a.querySelector(".z-label")?.textContent || a.textContent || "").trim();
    if (id && label && !/^(All items|New collection)$/i.test(label)) {
      a.dataset.collectionId = id;
      list.push({ id, label, el: a });
    }
  });
  return list;
}
async function assignIdsToCollection(ids, colId, op) {
  if (!ids?.length || !colId) return;
  const fd = new FormData();
  fd.append("csrfmiddlewaretoken", csrfToken());
  fd.append("op", op);
  ids.forEach(id => fd.append("ids", id));
  const resp = await fetch(`/collections/${colId}/assign/`, {
    method: "POST", body: fd, credentials: "same-origin",
    headers: {"X-CSRFToken": csrfToken()}
  });
  if (resp.redirected) { window.location.href = resp.url; return; }
  if (resp.ok) { window.location.reload(); return; }
  alert(`${op === "add" ? "Add to" : "Remove from"} collection failed (${resp.status}).`);
}
function idsFromSelection() {
  return [...state.selected];
}

// --- DnD to collections rail ---
function addDndHandlers(el, colId){
  on(el, "dragenter", (e) => { e.preventDefault(); el.classList.add("dnd-over"); });
  on(el, "dragover",  (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
  on(el, "dragleave", () => { el.classList.remove("dnd-over"); });
  on(el, "drop", async (e) => {
    e.preventDefault(); e.stopPropagation();
    el.classList.remove("dnd-over");
    try{
      const data = e.dataTransfer.getData("text/plain") || e.dataTransfer.getData("application/json");
      let obj = {};
      try { obj = JSON.parse(data || "{}"); } catch(_){}
      const ids = (obj.type === "pc-ids" && Array.isArray(obj.ids) && obj.ids.length) ? obj.ids : idsFromSelection();
      if (ids.length) await assignIdsToCollection(ids, colId, "add");
    } catch(err){ console.warn(err); }
  });
}
function wireCollectionsDnd(){
  const cols = scanCollections();
  cols.forEach(({ el, id }) => addDndHandlers(el, id));
}

// --- Row context menu (Add / Remove / Delete) ---
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
    const kind = li.getAttribute("data-sub");
    const box  = menuEl.getBoundingClientRect();
    const liBox= li.getBoundingClientRect();
    const el   = (kind === "remove") ? submenuRemoveEl : submenuAddEl;
    const other= (kind === "remove") ? submenuAddEl : submenuRemoveEl;
    other.style.display = "none";
    el.style.display = "block";
    el.style.left = (box.right + 2) + "px";
    el.style.top  = liBox.top + "px";
    keepOnScreen(el);
  });
  on(menuEl, "mouseleave", () => { submenuAddEl.style.display = "none"; submenuRemoveEl.style.display = "none"; });
  on(menuEl, "click", onRowMenuClick);

  // Close on outside interactions
  ["click","scroll","resize"].forEach(ev => on(window, ev, hideRowMenu, { passive:true }));
}
function keepOnScreen(el){
  const r = el.getBoundingClientRect();
  let nx = r.left, ny = r.top, changed = false;
  if (r.right > window.innerWidth)  { nx = Math.max(8, window.innerWidth  - r.width  - 8); changed = true; }
  if (r.bottom > window.innerHeight) { ny = Math.max(8, window.innerHeight - r.height - 8); changed = true; }
  if (changed) { el.style.left = nx + "px"; el.style.top = ny + "px"; }
}
function populateSubmenu(el, op) {
  const cols = scanCollections();
  const html = cols.map(c => `<div class="pc-subitem" data-col="${escapeHtml(c.id)}">${escapeHtml(c.label)}</div>`).join("") || `<div class="pc-subitem disabled">(no collections)</div>`;
  el.innerHTML = html;
  on(el, "click", (e) => {
    const d = e.target.closest(".pc-subitem"); if (!d || d.classList.contains("disabled")) return;
    const ids = idsFromSelection();
    assignIdsToCollection(ids, d.getAttribute("data-col"), op).catch(()=>{});
    hideRowMenu();
  }, { once: true });
}
function onRowMenuClick(e) {
  const actEl = e.target.closest("[data-act]"); if (!actEl) return;
  const act = actEl.getAttribute("data-act");
  if (act === "open") {
    const tr = document.querySelector("#pc-body tr.pc-row[aria-selected='true']") || document.querySelector("#pc-body tr.pc-row");
    if (tr) window.location.href = `/captures/${tr.dataset.id}/`;
  } else if (act === "open-ext") {
    const tr = document.querySelector("#pc-body tr.pc-row[aria-selected='true']") || document.querySelector("#pc-body tr.pc-row");
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
function hideRowMenu() { if (menuEl) menuEl.style.display = "none"; submenuAddEl.style.display = "none"; submenuRemoveEl.style.display = "none"; }
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

// --- Collections right-click (rename/delete) + modal ---
let colMenuEl = null, colMenuTarget = null;
function ensureColMenu(){
  if (colMenuEl) return;
  colMenuEl = document.createElement("div");
  colMenuEl.className = "pc-context";
  colMenuEl.innerHTML = `
    <ul class="pc-menu">
      <li data-act="open">Open</li>
      <li data-act="rename">Rename…</li>
      <li class="danger" data-act="delete">Delete…</li>
    </ul>
  `;
  document.body.appendChild(colMenuEl);
  on(colMenuEl, "click", onColMenuClick);
  ["click","scroll","resize"].forEach(ev => on(window, ev, hideColMenu, { passive:true }));
}
function onColMenuClick(e){
  const a = colMenuTarget;
  if (!a) return hideColMenu();
  const id = a.getAttribute("data-collection-id");
  const label = (a.querySelector(".z-label")?.textContent || "").trim();
  const act = e.target.closest("[data-act]")?.getAttribute("data-act");
  if (!act) return;

  if (act === "open") {
    window.location.href = a.href;
  } else if (act === "rename") {
    openModal({
      title: "Rename collection",
      initial: label,
      submitText: "Save",
      onSubmit: (val) => renameCollection(id, val)
    });
  } else if (act === "delete") {
    if (confirm(`Delete collection “${label}”? Items remain in All items.`)) {
      deleteCollection(id);
    }
  }
  hideColMenu();
}
function hideColMenu(){ if (colMenuEl) colMenuEl.style.display = "none"; colMenuTarget = null; }
function showColMenu(x, y, target){
  ensureColMenu();
  colMenuTarget = target;
  colMenuEl.style.display = "block";
  colMenuEl.style.left = x + "px";
  colMenuEl.style.top  = y + "px";
  const r = colMenuEl.getBoundingClientRect();
  if (r.right > innerWidth)  colMenuEl.style.left = Math.max(8, innerWidth  - r.width  - 8) + "px";
  if (r.bottom > innerHeight) colMenuEl.style.top  = Math.max(8, innerHeight - r.height - 8) + "px";
}

async function createCollection(name, parentId=null){
  if (!name) return false;
  const fd = new FormData();
  fd.append("csrfmiddlewaretoken", csrfToken());
  fd.append("name", name);
  if (parentId) fd.append("parent", parentId);
  const resp = await fetch("/collections/create/", {
    method:"POST", body: fd, credentials:"same-origin",
    headers: {"X-CSRFToken": csrfToken()}
  });
  if (resp.redirected) { window.location.href = resp.url; return true; }
  if (resp.ok) { window.location.reload(); return true; }
  alert("Create failed (" + resp.status + ")."); return false;
}
async function renameCollection(id, name){
  if (!id || !name) return false;
  const fd = new FormData();
  fd.append("csrfmiddlewaretoken", csrfToken());
  fd.append("name", name);
  const resp = await fetch(`/collections/${id}/rename/`, {
    method:"POST", body: fd, credentials:"same-origin",
    headers: {"X-CSRFToken": csrfToken()}
  });
  if (resp.redirected) { window.location.href = resp.url; return true; }
  if (resp.ok) { window.location.reload(); return true; }
  alert("Rename failed (" + resp.status + ")."); return false;
}
async function deleteCollection(id){
  if (!id) return false;
  const fd = new FormData();
  fd.append("csrfmiddlewaretoken", csrfToken());
  const resp = await fetch(`/collections/${id}/delete/`, {
    method:"POST", body: fd, credentials:"same-origin",
    headers: {"X-CSRFToken": csrfToken()}
  });
  if (resp.redirected) { window.location.href = resp.url; return true; }
  if (resp.ok) { window.location.reload(); return true; }
  alert("Delete failed (" + resp.status + ")."); return false;
}

// Modal
function openModal({ title, placeholder, initial, submitText, onSubmit }) {
  const modalEl    = $("#pc-modal");
  const modalTitle = $("#pc-modal-title");
  const modalInput = $("#pc-modal-input");
  const modalCancel= $("#pc-modal-cancel");
  const modalSubmit= $("#pc-modal-submit");
  if (!modalEl) return;

  modalTitle.textContent = title || "Input";
  modalInput.placeholder = placeholder || "";
  modalInput.value = initial || "";
  modalSubmit.textContent = submitText || "OK";

  function syncDisabled() { modalSubmit.disabled = !(modalInput.value.trim().length > 0); }
  modalInput.removeEventListener("input", syncDisabled);
  modalInput.addEventListener("input", syncDisabled);
  modalInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !modalSubmit.disabled) modalSubmit.click(); });
  syncDisabled();

  modalEl.style.display = "flex";
  modalEl.setAttribute("aria-hidden", "false");
  setTimeout(() => modalInput.focus(), 0);

  function close() { modalEl.style.display = "none"; modalEl.setAttribute("aria-hidden", "true"); modalSubmit.onclick = null; }
  modalCancel?.addEventListener("click", close, { once:true });
  modalEl?.addEventListener("click", (e) => { if (e.target === modalEl) close(); }, { once:true });
  window.addEventListener("keydown", (e) => { if (e.key === "Escape" && modalEl.style.display === "flex") close(); }, { once:true });
  modalSubmit.onclick = async () => {
    const ok = await onSubmit?.(modalInput.value.trim());
    if (ok !== false) close();
  };
}

// ---------- NEW: collapsible left-rail groups (Collections / Years / Journals / Sites) ----------
function initGroupCollapsers() {
  const left = document.getElementById("z-left");
  if (!left) return;

  const groups = [...left.querySelectorAll(".z-group")];
  groups.forEach((g, idx) => {
    if (g.dataset.collapserWired === "1") return; // don’t double-bind
    g.dataset.collapserWired = "1";

    const key = g.getAttribute("data-key") || `grp-${idx}`;
    g.setAttribute("data-key", key);

    const title = g.querySelector(".z-group-title") || g.querySelector(".z-group-header") || g.firstElementChild;
    if (title) {
      title.setAttribute("role", "button");
      title.setAttribute("tabindex", "0");
    }

    // restore state
    const saved = localStorage.getItem(`pc-collapse:${key}`);
    const collapsed = saved === "1";
    if (collapsed) g.classList.add("collapsed");
    if (title) title.setAttribute("aria-expanded", String(!collapsed));

    const toggle = () => {
      const willCollapse = !g.classList.contains("collapsed");
      g.classList.toggle("collapsed", willCollapse);
      if (title) title.setAttribute("aria-expanded", String(!willCollapse));
      try { localStorage.setItem(`pc-collapse:${key}`, willCollapse ? "1" : "0"); } catch {}
    };

    title && on(title, "click", toggle);
    title && on(title, "keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
    });
  });
}

export function initCollectionsAndContextMenus() {
  // NEW: make the left-rail groups collapsible (and remember state)
  initGroupCollapsers();

  // Top toolbar Assign buttons
  const select = $("#pc-assign-select");
  const addBtn = $("#pc-assign-add");
  const rmBtn  = $("#pc-assign-remove");
  addBtn?.addEventListener("click", () => {
    const colId = select?.value;
    if (!colId) return alert("Pick a collection first.");
    const ids = idsFromSelection();
    if (!ids.length) return alert("Select rows to assign.");
    assignIdsToCollection(ids, colId, "add");
  });
  rmBtn?.addEventListener("click", () => {
    const colId = select?.value;
    if (!colId) return alert("Pick a collection first.");
    const ids = idsFromSelection();
    if (!ids.length) return alert("Select rows to remove.");
    assignIdsToCollection(ids, colId, "remove");
  });

  // New collection button
  const colAddBtn = $("#pc-col-add-btn");
  colAddBtn?.addEventListener("click", () => {
    openModal({ title: "New collection", placeholder: "Name", submitText: "Create", onSubmit: (val) => createCollection(val) });
  });

  // Row right-click menu
  const tbody = document.getElementById("pc-body");
  on(tbody, "contextmenu", (e) => {
    const tr = e.target.closest("tr.pc-row");
    if (!tr) return;
    e.preventDefault();
    // Select the row if not in selection
    if (tr.getAttribute("aria-selected") !== "true") {
      document.querySelectorAll("#pc-body tr.pc-row[aria-selected='true']").forEach(x => x.setAttribute("aria-selected", "false"));
      tr.setAttribute("aria-selected", "true");
      state.selected = new Set([tr.dataset.id]);
    }
    showRowMenu(e.pageX, e.pageY);
  });

  // Collections right-click menu
  const zLeft = document.getElementById("z-left");
  on(zLeft, "contextmenu", (e) => {
    const link = e.target.closest(".z-link[data-collection-id]");
    if (!link) return;
    e.preventDefault();
    e.stopPropagation();
    showColMenu(e.pageX, e.pageY, link);
  });

  // Rewire DnD every time rows/rail change
  wireCollectionsDnd();
  on(document, "pc:rows-updated", wireCollectionsDnd);
}
