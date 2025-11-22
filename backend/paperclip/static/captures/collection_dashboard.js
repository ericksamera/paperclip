// services/server/paperclip/static/captures/collection_dashboard.js
// Small, dependency-light renderer for the per-collection dashboard.

function cssVar(name, fallback = "#e6edf3") {
  try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback; }
  catch(_) { return fallback; }
}

function setChartDefaults() {
  const fg = cssVar("--fg", "#e6edf3");
  const line = cssVar("--line", "#2f3742");
  Chart.defaults.color = fg;
  Chart.defaults.borderColor = line;
  Chart.defaults.font.family = "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif";
}

function barOpts({ horizontal = false, maxTicks = 6 } = {}) {
  return {
    indexAxis: horizontal ? "y" : "x",
    responsive: true,
    maintainAspectRatio: false,     // size to parent wrapper height
    resizeDelay: 120,               // soften resize storms
    animation: false,               // avoid layout thrash on first paint
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { autoSkip: true, maxTicksLimit: maxTicks }, grid: { color: cssVar("--line") } },
      y: { ticks: { autoSkip: true, maxTicksLimit: maxTicks }, grid: { color: cssVar("--line") } },
    },
  };
}

function dataFromPairs(pairs) {
  const labels = pairs.map(([k]) => String(k));
  const values = pairs.map(([, v]) => Number(v) || 0);
  return { labels, values };
}

async function fetchSummary(colId) {
  const r = await fetch(`/collections/${encodeURIComponent(colId)}/summary.json`, { credentials: "same-origin" });
  if (!r.ok) throw new Error("summary fetch failed: " + r.status);
  return await r.json();
}

function writeMeta(el, j) {
  const c = j.collection || {};
  const y = j.years_stats || {};
  const parts = [];
  parts.push(`<strong>${c.count || 0}</strong> item(s)`);
  if (y.min != null && y.max != null) parts.push(`years <strong>${y.min}</strong>–<strong>${y.max}</strong> (span ${y.span})`);
  if (y.mode != null) parts.push(`mode <strong>${y.mode}</strong>`);
  el.innerHTML = parts.join(" · ");
}

function renderCharts(j) {
  setChartDefaults();

  // Timeline
  const years = j.years || [];
  const labelsYears = years.map(d => String(d.label));
  const valuesYears = years.map(d => Number(d.count) || 0);
  new Chart(document.getElementById("pc-chart-years"), {
    type: "bar",
    data: { labels: labelsYears.reverse(), datasets: [{ data: valuesYears.reverse() }] },
    options: barOpts({ horizontal: false, maxTicks: 8 }),
  });

  // Journals
  const jn = dataFromPairs(j.journals || []);
  new Chart(document.getElementById("pc-chart-journals"), {
    type: "bar",
    data: { labels: jn.labels, datasets: [{ data: jn.values }] },
    options: barOpts({ horizontal: true, maxTicks: 6 }),
  });

  // Sites
  const st = dataFromPairs(j.sites || []);
  new Chart(document.getElementById("pc-chart-sites"), {
    type: "bar",
    data: { labels: st.labels, datasets: [{ data: st.values }] },
    options: barOpts({ horizontal: true, maxTicks: 6 }),
  });

  // Authors (family)
  const au = dataFromPairs(j.authors || []);
  new Chart(document.getElementById("pc-chart-authors"), {
    type: "bar",
    data: { labels: au.labels, datasets: [{ data: au.values }] },
    options: barOpts({ horizontal: true, maxTicks: 6 }),
  });
}

function wireGraphMount() {
  const btn = document.getElementById("pc-mount-graph");
  const host = document.getElementById("pc-graph-host");
  if (!btn || !host) return;
  btn.addEventListener("click", () => {
    host.style.display = "block";
    try {
      const iframe = document.getElementById("pc-graph-iframe");
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.postMessage({ type: "paperclip:set-theme", theme: document.documentElement.getAttribute("data-theme") || "dark" }, "*");
      }
    } catch (_) {}
    btn.disabled = true;
  }, { once: true });
}

(async function boot() {
  const colId = (window.PCDASH && window.PCDASH.collectionId) || null;
  if (!colId) return;

  try {
    const j = await fetchSummary(colId);
    writeMeta(document.getElementById("pc-dash-meta"), j);
    renderCharts(j);
  } catch (e) {
    console.warn(e);
    document.getElementById("pc-dash-meta").textContent = "Failed to load summary.";
  }

  wireGraphMount();
})();
