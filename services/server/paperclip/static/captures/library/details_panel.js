// captures/library/details_panel.js
// Keeps the right-hand details panel (#z-info) in sync with the current selection.
// Works with rows shaped like: <tr class="pc-row" data-id="…" data-title="…" data-authors="…" …>

import { $, $$, on, escapeHtml } from "./dom.js";

function truncate(s, n) {
  const t = String(s || "");
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
}
function safeHost(u) {
  try { return new URL(u, location.href).hostname; } catch { return ""; }
}
function openRightPane() {
  const shell = $("#z-shell");
  if (!shell) return;
  const stored = localStorage.getItem("pc-right-w") || "360px";
  shell.style.setProperty("--right-w", stored);
}

function oneRowHtml(tr) {
  const title   = tr.dataset.title || "(Untitled)";
  const url     = tr.dataset.url || "";
  const site    = safeHost(url);
  const authors = tr.dataset.authors || "";
  const journal = tr.dataset.journal || "";
  const year    = tr.dataset.year || "";
  const doi     = tr.dataset.doi || "";
  const doiUrl  = tr.dataset.doiUrl || (doi ? "https://doi.org/" + doi : "");
  const abs     = tr.dataset.abstract || "";
  const kws     = (tr.dataset.keywords || "").split(",").map(s => s.trim()).filter(Boolean);

  return `
    <h3>${escapeHtml(title)}</h3>
    <div class="z-meta">
      ${journal ? escapeHtml(journal) + " · " : ""}${year ? escapeHtml(year) + " · " : ""}${site ? escapeHtml(site) : ""}
    </div>
    ${authors ? `<div class="z-meta">${escapeHtml(authors)}</div>` : ""}
    ${doi ? `<div class="z-meta"><a href="${escapeHtml(doiUrl)}" target="_blank" rel="noopener">${escapeHtml(doi)}</a></div>` : ""}
    ${abs ? `<div class="z-meta"><strong>Abstract.</strong> ${escapeHtml(truncate(abs, 700))}</div>` : ""}
    ${kws.length ? `<div class="z-kws">${kws.map(k => `<span class="z-kw">${escapeHtml(k)}</span>`).join("")}</div>` : ""}
  `;
}

function updateInfoPanel() {
  const info = $("#z-info");
  if (!info) return;

  const rows = $$("#pc-body tr.pc-row[aria-selected='true']");
  if (rows.length === 1) {
    info.innerHTML = oneRowHtml(rows[0]);
    openRightPane();
  } else if (rows.length > 1) {
    info.innerHTML = `<div class="z-meta">${rows.length} items selected.</div>`;
    openRightPane();
  } else {
    info.innerHTML = `<div class="z-info-empty">Select an item to see details.</div>`;
  }
}

export function initDetailsPanel() {
  // Initial render (in case the server preselected something)
  updateInfoPanel();

  // When selection changes (from selection.js), refresh the panel
  document.addEventListener("pc:selection-change", updateInfoPanel);

  // When rows are swapped/appended by search/paging, refresh (will usually show the empty state)
  document.addEventListener("pc:rows-updated", updateInfoPanel);
  document.addEventListener("pc:rows-replaced", updateInfoPanel);

  // Belt & suspenders: if some legacy code toggles selection on click but doesn’t fire the event,
  // we still update on clicks inside the table.
  on(document, "click", (e) => {
    if (e.target.closest && e.target.closest("#pc-body tr.pc-row")) {
      // Let selection handlers run first.
      setTimeout(updateInfoPanel, 0);
    }
  }, { capture: true });
}
