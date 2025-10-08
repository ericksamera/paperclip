// services/server/paperclip/static/captures/library/years_hist.js
// PubMed-style year histogram + dual range + numeric inputs.
// Robust mount (find group by key or header text), retries + MutationObserver,
// never double-mounts, and writes ?year=YYYY-YYYY | YYYY+ | <=YYYY.

import { on } from "./dom.js";

const MOUNT_ATTR = "data-pc-years-mounted";

/* ---------- tiny DOM helpers ---------- */
function $(sel, root = document) { return root.querySelector(sel); }
function $all(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

/* ---------- URL helpers ---------- */
function readCurrentRange() {
  const u = new URL(location.href);
  const raw = (u.searchParams.get("year") || "").trim();
  if (!raw) return null;

  let m = raw.match(/^(\d{4})[-:](\d{4})$/);
  if (m) {
    const a = parseInt(m[1], 10), b = parseInt(m[2], 10);
    return { min: Math.min(a, b), max: Math.max(a, b) };
  }
  m = raw.match(/^(\d{4})\+$/) || raw.match(/^>=?(\d{4})$/);
  if (m) return { min: parseInt(m[1], 10), max: null };
  m = raw.match(/^<=?(\d{4})$/);
  if (m) return { min: null, max: parseInt(m[1], 10) };
  return null;
}

function setQueryRange(minY, maxY) {
  const url = new URL(location.href);
  url.searchParams.delete("page"); // reset paging any time year changes
  if (minY == null && maxY == null) {
    url.searchParams.delete("year");
  } else if (minY != null && maxY != null) {
    url.searchParams.set("year", `${Math.min(minY, maxY)}-${Math.max(minY, maxY)}`);
  } else if (minY != null) {
    url.searchParams.set("year", `${minY}+`);
  } else if (maxY != null) {
    url.searchParams.set("year", `<=${maxY}`);
  }
  location.assign(url.toString());
}

/* ---------- find the Years group reliably ---------- */
function findYearsGroup() {
  // 1) explicit key or id (preferred)
  let g =
    document.querySelector(".z-group[data-key='grp-years']") ||
    document.getElementById("grp-years");
  if (g) return g;

  // 2) any .z-group whose header text starts with "Years"
  for (const grp of document.querySelectorAll(".z-group")) {
    const header = grp.querySelector(
      ".z-group-header, .z-group-title, .z-head, .z-title, header, h2, h3, h4"
    );
    const text = (header?.textContent || "").trim().toLowerCase();
    if (/^years\b/.test(text)) return grp;
  }

  // 3) fallback: any facet container labeled Years
  const hint = document.querySelector(
    "[data-facet='years'], .facet-years, [aria-label='Years']"
  );
  return hint?.closest(".z-group") || hint || null;
}

/* ---------- harvest existing per-year rows ---------- */
function inferYearsFromGroup(group) {
  const rows = [];
  $all("li", group).forEach((li) => {
    const txt = (li.textContent || "").trim();
    const ym = txt.match(/\b(19|20)\d{2}\b/);
    if (!ym) return;
    const year = parseInt(ym[0], 10);

    let count = 0;
    const badge = li.querySelector(".z-badge, .count, .facet-count");
    if (badge && /\d+/.test(badge.textContent || "")) {
      count = parseInt((badge.textContent || "").replace(/[^\d]/g, ""), 10);
    } else {
      const cm = txt.match(/(\d+)\s*$/);
      count = cm ? parseInt(cm[1], 10) : 0;
    }
    rows.push({ year, count: isNaN(count) ? 0 : count, li });
  });

  const byYear = new Map();
  rows.forEach(({ year, count }) => byYear.set(year, (byYear.get(year) || 0) + count));
  return Array.from(byYear, ([year, count]) => ({ year, count })).sort((a, b) => a.year - b.year);
}

/* ---------- rendering ---------- */
function paintBars(chartEl, data, range) {
  chartEl.innerHTML = "";
  if (!data.length) return;

  const maxC = Math.max(...data.map((d) => d.count), 1);
  data.forEach((d) => {
    const bar = document.createElement("div");
    bar.className = "pc-years-bar";
    bar.style.height = `${Math.round((d.count / maxC) * 100)}%`;
    bar.title = `${d.year} · ${d.count}`;
    if (range && (range.min ?? -Infinity) <= d.year && d.year <= (range.max ?? Infinity)) {
      bar.classList.add("in-range");
    }
    // Clicking a bar moves the nearest bound to that year
    bar.addEventListener("click", () => {
      const wrap = chartEl.parentElement;
      const minInput = wrap.querySelector("input[data-role=min-year]");
      const maxInput = wrap.querySelector("input[data-role=max-year]");
      const minV = parseInt(minInput.value, 10);
      const maxV = parseInt(maxInput.value, 10);
      const mid = (minV + maxV) / 2;
      if (isNaN(minV) || d.year <= mid) minInput.value = String(d.year);
      else maxInput.value = String(d.year);
      minInput.dispatchEvent(new Event("input", { bubbles: true }));
      maxInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    chartEl.appendChild(bar);
  });
}

function clamp(v, lo, hi) {
  return Math.min(hi, Math.max(lo, v));
}

/* ---------- build + mount widget ---------- */
function buildWidget(group) {
  // Already mounted?
  if (!group || group.getAttribute(MOUNT_ATTR) === "1") return true;

  const data = inferYearsFromGroup(group);
  if (!data.length) return false;

  const years = data.map((d) => d.year);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);

  // Host area inside the group
  const host =
    group.querySelector(".z-list, .z-body, .z-group-body, .facet-body") || group;

  // Widget skeleton
  const wrap = document.createElement("div");
  wrap.className = "pc-years";
  wrap.innerHTML = `
    <div class="pc-years-axis"><span>${minYear}</span><span>${maxYear}</span></div>
    <div class="pc-years-chart"></div>
    <div class="pc-years-slider">
      <input type="range" data-role="min" min="${minYear}" max="${maxYear}" value="${minYear}" step="1">
      <input type="range" data-role="max" min="${minYear}" max="${maxYear}" value="${maxYear}" step="1">
    </div>
    <div class="pc-years-controls">
      <input type="number" data-role="min-year" min="${minYear}" max="${maxYear}" value="${minYear}">
      <span class="sep">—</span>
      <input type="number" data-role="max-year" min="${minYear}" max="${maxYear}" value="${maxYear}">
      <button class="btn" data-role="clear">Clear</button>
      <button class="btn btn--primary" data-role="apply">Apply</button>
    </div>
  `;

  // Insert widget at top, hide legacy list
  if (host.firstChild) host.insertBefore(wrap, host.firstChild);
  else host.appendChild(wrap);

  $all("ul, ol, .facet-list, [data-facet-list]", host).forEach((el) => {
    el.hidden = true;
  });

  // Init range from URL
  const cur = readCurrentRange();
  const range = {
    min: clamp(cur?.min ?? minYear, minYear, maxYear),
    max: clamp(cur?.max ?? maxYear, minYear, maxYear),
  };
  $("input[data-role=min]", wrap).value = String(range.min);
  $("input[data-role=max]", wrap).value = String(range.max);
  $("input[data-role=min-year]", wrap).value = String(range.min);
  $("input[data-role=max-year]", wrap).value = String(range.max);

  // Draw chart
  const chart = $(".pc-years-chart", wrap);
  paintBars(chart, data, range);

  // Sync helpers
  const syncFromSliders = () => {
    let lo = parseInt($("input[data-role=min]", wrap).value, 10);
    let hi = parseInt($("input[data-role=max]", wrap).value, 10);
    if (lo > hi) [lo, hi] = [hi, lo];
    $("input[data-role=min]", wrap).value = String(lo);
    $("input[data-role=max]", wrap).value = String(hi);
    $("input[data-role=min-year]", wrap).value = String(lo);
    $("input[data-role=max-year]", wrap).value = String(hi);
    paintBars(chart, data, { min: lo, max: hi });
  };

  const syncFromInputs = () => {
    let lo = clamp(parseInt($("input[data-role=min-year]", wrap).value, 10), minYear, maxYear);
    let hi = clamp(parseInt($("input[data-role=max-year]", wrap).value, 10), minYear, maxYear);
    if (isNaN(lo)) lo = minYear;
    if (isNaN(hi)) hi = maxYear;
    if (lo > hi) [lo, hi] = [hi, lo];
    $("input[data-role=min-year]", wrap).value = String(lo);
    $("input[data-role=max-year]", wrap).value = String(hi);
    $("input[data-role=min]", wrap).value = String(lo);
    $("input[data-role=max]", wrap).value = String(hi);
    paintBars(chart, data, { min: lo, max: hi });
  };

  // Events
  on(wrap, "input", (e) => {
    const t = e.target;
    if (t.matches("input[type=range]")) syncFromSliders();
    if (t.matches("input[type=number]")) syncFromInputs();
  });

  on(wrap, "click", (e) => {
    if (e.target.closest("[data-role=apply]")) {
      const a = parseInt($("input[data-role=min-year]", wrap).value, 10);
      const b = parseInt($("input[data-role=max-year]", wrap).value, 10);
      setQueryRange(isNaN(a) ? null : a, isNaN(b) ? null : b);
    }
    if (e.target.closest("[data-role=clear]")) {
      setQueryRange(null, null);
    }
  });

  // Mark mounted so we never double-insert
  group.setAttribute(MOUNT_ATTR, "1");
  return true;
}

/* ---------- public init (with retries + observer) ---------- */
export function initYearsWidget() {
  let attempts = 0;

  const tryMount = () => {
    attempts += 1;
    const group = findYearsGroup();
    if (!group) {
      if (attempts < 10) requestAnimationFrame(tryMount);
      return;
    }
    if (buildWidget(group)) return; // success
    if (attempts < 10) requestAnimationFrame(tryMount);
  };

  tryMount();

  // If left rail is dynamically updated later, mount then.
  const left = document.querySelector(".z-left") || document.querySelector(".sidebar") || document.body;
  const obs = new MutationObserver(() => {
    const group = findYearsGroup();
    if (group && group.getAttribute(MOUNT_ATTR) !== "1") {
      if (buildWidget(group)) obs.disconnect();
    }
  });
  obs.observe(left, { childList: true, subtree: true });
}
