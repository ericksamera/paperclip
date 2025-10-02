// services/server/paperclip/static/captures/library/details_panel.js
// Renders the right-hand details panel for the selected rows.

import { $, $$, on, escapeHtml } from "./dom.js";
import { onRowsChanged, EVENTS } from "./events.js";

function truncate(s, n) {
  const x = String(s ?? "");
  return x.length > n ? (x.slice(0, n - 1) + "…") : x;
}

function oneRowHtml(row) {
  const title   = row.getAttribute("data-title")    || "";
  const doi     = row.getAttribute("data-doi")      || "";
  const doiUrl  = row.getAttribute("data-doi-url")  || (doi ? `https://doi.org/${encodeURIComponent(doi)}` : "");
  const journal = row.getAttribute("data-journal")  || "";
  const authors = row.getAttribute("data-authors")  || "";
  const abs     = row.getAttribute("data-abstract") || "";
  const site    = row.getAttribute("data-site")     || "";
  const year    = row.getAttribute("data-year")     || "";

  // NEW: keywords (already provided on each row as data-keywords)
  // Accept comma or semicolon separators, trim, and drop empties.
  const kwRaw = row.getAttribute("data-keywords") || "";
  const kws = kwRaw.split(/[;,]/).map(s => s.trim()).filter(Boolean);
  const kwsHtml = kws.length
    ? `<div class="z-kws">${kws.map(k => `<span class="z-kw">${escapeHtml(k)}</span>`).join("")}</div>`
    : "";

  return `
    <h3>${escapeHtml(title)}</h3>
    <div class="z-meta">
      ${journal ? escapeHtml(journal) + " · " : ""}${year ? escapeHtml(year) + " · " : ""}${site ? escapeHtml(site) : ""}
    </div>
    ${authors ? `<div class="z-meta">${escapeHtml(authors)}</div>` : ""}
    ${doi ? `<div class="z-meta"><a href="${escapeHtml(doiUrl)}" target="_blank" rel="noopener">${escapeHtml(doi)}</a></div>` : ""}
    ${abs ? `<div class="z-meta"><strong>Abstract.</strong> ${escapeHtml(truncate(abs, 700))}</div>` : ""}
    ${kwsHtml}
  `;
}

function updateInfoPanel() {
  const info = $("#z-info");
  if (!info) return;

  const rows = $$("#pc-body tr.pc-row[aria-selected='true']");
  if (rows.length === 1) {
    info.innerHTML = oneRowHtml(rows[0]);
    if (typeof window.openRightPane === "function") window.openRightPane();
  } else if (rows.length > 1) {
    info.innerHTML = `<div class="z-meta">${rows.length} items selected.</div>`;
    if (typeof window.openRightPane === "function") window.openRightPane();
  } else {
    info.innerHTML = `<div class="z-info-empty">Select an item to see details.</div>`;
  }
}

export function initDetailsPanel() {
  // Initial render (in case the server preselected something)
  updateInfoPanel();

  // When selection changes, refresh the panel
  document.addEventListener(EVENTS.SELECTION, updateInfoPanel);

  // Refresh on canonical rows-changed. The legacy bridge is now centralized in events.js.
  onRowsChanged(updateInfoPanel);

  // Belt & suspenders: if some legacy code toggles selection on click but doesn’t fire the event,
  // we still update on clicks inside the table.
  on(
    document,
    "click",
    (e) => {
      if (e.target.closest && e.target.closest("#pc-body tr.pc-row")) {
        // Let selection handlers run first.
        setTimeout(updateInfoPanel, 0);
      }
    },
    { capture: true }
  );
}
