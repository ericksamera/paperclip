// services/server/paperclip/static/captures/library/features/columns_panels.js
// Columns drawer (show/hide + reorder) and basic panel wiring.
// Uses infra/dom + infra/events; no imports from selection.js.

import { qsa, on } from "../infra/dom.js";
import { EVENTS } from "../infra/events.js";

// Local storage keys
const COL_ORDER_KEY = "pc-col-order";
const COL_VIS_KEY = "pc-col-visible";

function readLS(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeLS(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

function applyVisibility(vis) {
  // vis is a dict { columnKey: true/false }
  qsa("[data-col-key]").forEach((el) => {
    const k = el.getAttribute("data-col-key");
    if (!k) return;
    const on = vis[k] !== false; // default visible
    el.style.display = on ? "" : "none";
  });
}

function applyOrder(order) {
  if (!Array.isArray(order) || !order.length) return;
  const head = document.querySelector("thead tr");
  const body = document.getElementById("pc-body");
  if (!head || !body) return;

  // Reorder THs
  order.forEach((k) => {
    const th = head.querySelector(`th[data-col-key="${CSS.escape(k)}"]`);
    if (th) head.appendChild(th);
  });

  // Reorder each row's TDs to match
  body.querySelectorAll("tr.pc-row").forEach((tr) => {
    order.forEach((k) => {
      const td = tr.querySelector(`td[data-col-key="${CSS.escape(k)}"]`);
      if (td) tr.appendChild(td);
    });
  });
}

function currentColumns() {
  const headers = Array.from(document.querySelectorAll("thead th[data-col-key]"));
  return headers.map((th) => th.getAttribute("data-col-key")).filter(Boolean);
}

function buildDrawer() {
  let drawer = document.getElementById("pc-cols-drawer");
  if (drawer) return drawer;

  drawer = document.createElement("div");
  drawer.id = "pc-cols-drawer";
  drawer.className = "pc-drawer";
  drawer.innerHTML = `
    <div class="backdrop" aria-hidden="true"></div>
    <div class="panel" role="dialog" aria-modal="true" aria-label="Columns">
      <header style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px">
        <div>
          <div style="font-weight:600">Columns</div>
          <div style="font-size:12px;color:var(--muted-fg,#64748b)">
            Show, hide, and reorder table columns.
          </div>
        </div>
        <button type="button" class="btn btn--icon" id="pc-cols-close" aria-label="Close columns panel">
          ✕
        </button>
      </header>

      <ul class="pc-cols-list" id="pc-cols-list"></ul>

      <div style="margin-top:8px;font-size:12px;color:var(--muted-fg,#64748b)">
        Tip: Press <kbd>C</kbd> while in the table to open this panel.
      </div>

      <div style="margin-top:10px;display:flex;gap:8px;justify-content:flex-end">
        <button type="button" class="btn" id="pc-cols-close-footer">Close</button>
      </div>
    </div>
  `;
  document.body.appendChild(drawer);

  // Basic interactions
  const close = () => drawer.classList.remove("open");
  drawer.querySelector(".backdrop")?.addEventListener("click", close);
  drawer.querySelector("#pc-cols-close")?.addEventListener("click", close);
  drawer.querySelector("#pc-cols-close-footer")?.addEventListener("click", close);
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawer.classList.contains("open")) close();
  });

  return drawer;
}

function hydrateList(drawer, order, vis) {
  const ul = drawer.querySelector("#pc-cols-list");
  ul.innerHTML = "";
  const cols = currentColumns();

  const safeOrder = order && order.length ? order : cols.slice();
  const finalOrder = safeOrder.filter((k) => cols.includes(k)); // drop unknowns

  finalOrder.forEach((k) => {
    const li = document.createElement("li");
    li.className = "pc-cols-item";
    li.setAttribute("draggable", "true");
    li.dataset.key = k;
    li.innerHTML = `
      <span class="handle" title="Drag to reorder">≡</span>
      <span class="label">${k}</span>
      <input type="checkbox" ${
        vis?.[k] === false ? "" : "checked"
      } aria-label="Toggle ${k}">
    `;
    ul.appendChild(li);

    // Drag reorder
    li.addEventListener("dragstart", () => {
      li.classList.add("dragging");
    });
    li.addEventListener("dragend", () => {
      li.classList.remove("dragging");
      const keys = Array.from(ul.querySelectorAll(".pc-cols-item")).map(
        (n) => n.dataset.key
      );
      writeLS(COL_ORDER_KEY, keys);
      applyOrder(keys);
    });
  });

  // Dragover to reinsert above/below
  ul.addEventListener("dragover", (e) => {
    e.preventDefault();
    const cur = ul.querySelector(".pc-cols-item.dragging");
    if (!cur) return;
    const after = Array.from(ul.querySelectorAll(".pc-cols-item:not(.dragging)")).find(
      (n) => e.clientY <= n.getBoundingClientRect().top + n.offsetHeight / 2
    );
    if (after) ul.insertBefore(cur, after);
    else ul.appendChild(cur);
  });

  // Visibility toggles
  ul.addEventListener("change", (e) => {
    const li = e.target.closest(".pc-cols-item");
    if (!li) return;
    const k = li.dataset.key;
    const checked = e.target.checked;
    const next = { ...(vis || {}) };
    next[k] = !!checked;
    writeLS(COL_VIS_KEY, next);
    applyVisibility(next);
  });
}

export function initPanelsAndColumns() {
  const toggleBtn = document.getElementById("pc-cols-toggle");
  if (!toggleBtn) return;

  const drawer = buildDrawer();

  const savedOrder = readLS(COL_ORDER_KEY, null);
  const savedVis = readLS(COL_VIS_KEY, {});
  if (savedOrder) applyOrder(savedOrder);
  applyVisibility(savedVis);

  hydrateList(drawer, savedOrder, savedVis);

  // Open/close from toolbar button
  on(toggleBtn, "click", (e) => {
    e.preventDefault();
    hydrateList(
      drawer,
      readLS(COL_ORDER_KEY, currentColumns()),
      readLS(COL_VIS_KEY, {})
    );
    drawer.classList.add("open");
  });

  // Keyboard shortcut: C opens columns (kept here so selection.js stays focused)
  window.addEventListener("keydown", (e) => {
    const t = (e.target && (e.target.tagName || "")).toLowerCase();
    const typing = t === "input" || t === "textarea" || e.target?.isContentEditable;
    if (typing) return;
    if (!drawer.classList.contains("open") && e.key.toLowerCase() === "c") {
      e.preventDefault();
      hydrateList(
        drawer,
        readLS(COL_ORDER_KEY, currentColumns()),
        readLS(COL_VIS_KEY, {})
      );
      drawer.classList.add("open");
    }
  });

  // Re-hydrate the list whenever headers change (rare, but safe)
  document.addEventListener(
    EVENTS.ROWS_CHANGED,
    () => {
      hydrateList(
        drawer,
        readLS(COL_ORDER_KEY, currentColumns()),
        readLS(COL_VIS_KEY, {})
      );
    },
    { capture: true }
  );
}
