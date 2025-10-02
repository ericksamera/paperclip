// captures/library/search_paging.js
// Search mode chips, debounced search-as-you-type, table swapping, infinite scroll.
// Emits BOTH `pc:rows-replaced` and `pc:rows-updated` to keep consumers in sync.

import { $, $$, on, escapeHtml, buildQs } from "./dom.js";
import { state } from "./state.js";

function setSearchLoading(onFlag) {
  const z = $(".z-search");
  if (z) z.classList.toggle("is-loading", !!onFlag);
}

function setModeUI(targetMode) {
  $$(".z-mode-chip").forEach(btn => {
    const on = (btn.dataset.mode || "") === (targetMode || "");
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", String(on));
  });
}

export async function fetchAndReplaceTable(url, signal) {
  const resp = await fetch(url, { headers: { "X-Requested-With": "fetch" }, signal });
  if (!resp.ok) return false;
  const html = await resp.text();
  const doc = new DOMParser().parseFromString(html, "text/html");
  const newBody = doc.querySelector("#pc-body");
  if (!newBody) return false;

  const tbody = $("#pc-body");
  tbody.innerHTML = newBody.innerHTML;

  // Notify both names (legacy) + the canonical one
  document.dispatchEvent(new CustomEvent("pc:rows-replaced"));
  document.dispatchEvent(new CustomEvent("pc:rows-updated"));
  document.dispatchEvent(new CustomEvent("pc:rows-changed"));
  return true;
}

export function initSearchAndPaging() {
  const searchInput = document.querySelector(".z-search input[name=q]");
  const searchModeInput = document.querySelector(".z-search input[name=search]");
  const modeChips = $$(".z-mode-chip");
  const zCenter = document.querySelector(".z-center");

  // Chips -> set mode + fetch
  modeChips.forEach(btn => {
    on(btn, "click", async (e) => {
      e.preventDefault();
      const mode = btn.dataset.mode || "";
      if (searchModeInput) searchModeInput.value = mode;
      setModeUI(mode);
      setSearchLoading(true);
      try {
        const url = buildQs({ search: (mode || null), q: (searchInput?.value || "").trim() || null, page: null });
        const ok = await fetchAndReplaceTable(url);
        if (ok) pushUrl(url);
      } finally {
        setSearchLoading(false);
        if (searchInput) {
          searchInput.focus();
          const L = searchInput.value.length;
          searchInput.setSelectionRange(L, L);
        }
      }
    });
  });

  // Initialize chip UI to current URL
  setModeUI(
    new URL(location.href).searchParams.get("search") ||
    (document.querySelector(".z-search input[name=search]")?.value || "")
  );

  // Debounced search-as-you-type
  let searchTimer = null;
  let searchAbort = null;
  on(searchInput, "input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      setSearchLoading(true);
      try {
        if (searchAbort) searchAbort.abort();
        const ctl = new AbortController(); searchAbort = ctl;
        const url = buildQs({ q: (searchInput?.value || "") || null, page: null });
        const ok = await fetchAndReplaceTable(url, ctl.signal);
        if (ok) pushUrl(url);
      } catch {
        /* ignore */
      } finally {
        setSearchLoading(false);
        if (searchInput) {
          searchInput.focus();
          const L = searchInput.value.length;
          searchInput.setSelectionRange(L, L);
        }
      }
    }, 250);
  });

  // Infinite scroll
  if (zCenter) {
    on(zCenter, "scroll", () => maybeLoadMore(), { passive: true });
    prefetchMeta();
  }

  // Build filter chips under toolbar
  initChips();
}

/* ------------------- Row builder + pagination helpers ------------------- */

function rowHtml(r) {
  const title = escapeHtml(r.title || r.url || "(Untitled)");
  const url   = r.url ? `<div class="pc-link"><a href="${escapeHtml(r.url)}" target="_blank" rel="noreferrer">${escapeHtml(r.site_label || "")}</a></div>` : "";
  const doi   = r.doi_url ? `<a href="${escapeHtml(r.doi_url)}" target="_blank" rel="noreferrer">${escapeHtml(r.doi)}</a>` : "";
  const authorsTitle = escapeHtml(r.authors_intext || "");
  const journalCell = `<td class="pc-col-tight" data-col="journal" title="${escapeHtml(r.journal || "")}">${escapeHtml(r.journal_short || r.journal || "")}</td>`;
  const snippet = r.preview ? `<div class="pc-snippet">${escapeHtml(r.preview)}</div>` : "";
  return `
<tr class="pc-row" draggable="true" data-id="${r.id}" aria-selected="false"
    data-title="${escapeHtml(r.title)}"
    data-authors="${authorsTitle}"
    data-year="${escapeHtml(r.year || "")}"
    data-journal="${escapeHtml(r.journal || "")}"
    data-doi="${escapeHtml(r.doi || "")}"
    data-doi-url="${escapeHtml(r.doi_url || "")}"
    data-url="${escapeHtml(r.url || "")}"
    data-abstract="${escapeHtml(r.abstract || "")}"
    data-keywords="${escapeHtml((r.keywords || []).join(", "))}">
  <td class="pc-col-title" data-col="title">
    <a class="pc-title" href="/captures/${r.id}/">${title}</a>
    ${url}
    ${snippet}
  </td>
  <td class="pc-col-tight" data-col="authors"><span class="pc-authors-inline" title="${authorsTitle}">${authorsTitle}</span></td>
  <td class="pc-col-tight" data-col="year">${escapeHtml(r.year || "")}</td>
  ${journalCell}
  <td class="pc-col-tight" data-col="doi">${doi}</td>
  <td class="pc-col-tight" data-col="added">${escapeHtml(r.added || "")}</td>
  <td class="pc-col-tight" data-col="refs">${escapeHtml(String(r.refs ?? ""))}</td>
</tr>`;
}

async function fetchPage(pageNo) {
  const base = new URL(location.origin + "/library/page/");
  const cur = new URL(location.href);
  cur.searchParams.forEach((v, k) => base.searchParams.set(k, v));
  if (!base.searchParams.get("per")) base.searchParams.set("per", "200");
  base.searchParams.set("page", String(pageNo));
  const r = await fetch(base.toString(), { credentials: "same-origin" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

function updateScrollStatus() {
  const el = document.getElementById("pc-scroll-status") ||
             (() => { const d = document.createElement("div"); d.id = "pc-scroll-status"; d.className = "pc-scroll-status"; document.getElementById("z-shell").appendChild(d); return d; })();
  if (state.total == null) { el.textContent = ""; return; }
  const loaded = document.querySelectorAll("#pc-body tr.pc-row").length;
  el.textContent = `Loaded ${loaded} of ${state.total}`;
}

export async function ensureInitialRows() {
  const tbody = document.getElementById("pc-body");
  if (!tbody) return;
  if (tbody.querySelector("tr.pc-row")) return;
  try {
    state.loading = true;
    const j = await fetchPage(1);
    const rows = j.rows || [];
    if (rows.length) {
      tbody.innerHTML = rows.map(rowHtml).join("");
      state.nextPage = j?.page?.next_page ?? null;
      state.total = j?.page?.total ?? null;
      document.dispatchEvent(new CustomEvent("pc:rows-replaced"));
      document.dispatchEvent(new CustomEvent("pc:rows-updated"));
      document.dispatchEvent(new CustomEvent("pc:rows-changed"));
      updateScrollStatus();
    }
  } catch (e) {
    console.warn(e);
  } finally {
    state.loading = false;
  }
}


async function prefetchMeta() {
  try {
    const j = await fetchPage(1);
    state.total = j?.page?.total ?? null;
    state.nextPage = j?.page?.next_page ?? null;
    updateScrollStatus();
  } catch (_) {}
}

async function maybeLoadMore() {
  if (state.loading || state.nextPage == null) return;
  const zCenter = document.querySelector(".z-center");
  if (!zCenter) return;
  const nearBottom = (zCenter.scrollHeight - zCenter.scrollTop - zCenter.clientHeight) < 600;
  if (!nearBottom) return;

  state.loading = true;
  try {
    const j = await fetchPage(state.nextPage);
    const rows = j.rows || [];
    if (rows.length) {
      const html = rows.map(rowHtml).join("");
      document.getElementById("pc-body").insertAdjacentHTML("beforeend", html);
      document.dispatchEvent(new CustomEvent("pc:rows-updated"));
      document.dispatchEvent(new CustomEvent("pc:rows-changed"));
    }
    state.nextPage = j?.page?.next_page ?? null;
    updateScrollStatus();
  } catch (e) {
    console.warn(e);
  } finally {
    state.loading = false;
  }
}

/* ------------------- Chips (filters summary) ------------------- */

function initChips() {
  const toolbar = document.querySelector(".z-toolbar");
  if (!toolbar) return;
  const host = document.createElement("div");
  host.id = "pc-chips";
  host.style.marginLeft = "8px";
  host.style.display = "flex";
  host.style.flexWrap = "wrap";
  host.style.gap = "6px";
  const after = document.querySelector(".z-search") || toolbar.firstElementChild;
  after?.insertAdjacentElement("afterend", host);

  function chip(label, onClose) {
    const a = document.createElement("a");
    a.className = "chip";
    a.href = "#";
    a.innerHTML = `${escapeHtml(label)}&nbsp;✕`;
    a.addEventListener("click", (e) => { e.preventDefault(); onClose(); });
    return a;
  }
  const u = new URL(location.href);
  const params = {};
  u.searchParams.forEach((v, k) => { if (v !== "") params[k] = v; });

  const colLabelFromDOM = document.querySelector(".z-left .z-group:first-child .z-link.active .z-label")?.textContent?.trim() || null;
  if (params.year) host.appendChild(chip(`Year: ${params.year}`,    () => location.search = buildQs({ year: null })));
  if (params.journal) host.appendChild(chip(`Journal`,              () => location.search = buildQs({ journal: null })));
  if (params.site) host.appendChild(chip(`Site: ${params.site}`,    () => location.search = buildQs({ site: null })));
  if (params.col) host.appendChild(chip(`Collection: ${colLabelFromDOM || params.col}`, () => location.search = buildQs({ col: null })));
  if (!host.childElementCount) host.remove();
}
