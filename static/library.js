(function () {
  const selectAll = document.getElementById("select-all");
  const clearBtn = document.getElementById("clear-selection");
  const selectedCountEl = document.getElementById("selected-count");

  const tbody = document.getElementById("library-tbody");
  const sentinel = document.getElementById("infinite-sentinel");
  const loadingEl = document.getElementById("infinite-loading");
  const endEl = document.getElementById("infinite-end");
  const errorEl = document.getElementById("infinite-error");
  const cfgEl = document.getElementById("library-config");

  const pageSizeSelect = document.getElementById("page-size");
  const searchForm = document.getElementById("search-form");
  if (pageSizeSelect && searchForm) {
    pageSizeSelect.addEventListener("change", () => searchForm.submit());
  }

  // Prevent the "two clicks" from a double-click from visually toggling selection.
  let suppressClickToggle = false;
  function suppressClickFor(ms = 250) {
    suppressClickToggle = true;
    window.setTimeout(() => {
      suppressClickToggle = false;
    }, ms);
  }

  // --- Shift-click range selection (Gmail-style) ---
  let anchorRowIndex = null;

  function allRows() {
    if (!tbody || !tbody.querySelectorAll) return [];
    return Array.from(tbody.querySelectorAll("tr.cap-row"));
  }

  function rowIndex(row) {
    const rows = allRows();
    const i = rows.indexOf(row);
    return i >= 0 ? i : null;
  }

  function allBoxes() {
    return document.querySelectorAll(
      'input[type="checkbox"][name="capture_ids"]',
    );
  }

  function selectedCount() {
    let n = 0;
    allBoxes().forEach((b) => {
      if (b.checked) n += 1;
    });
    return n;
  }

  function setRowSelectedClass(row, on) {
    if (!row || !row.classList) return;
    if (on) row.classList.add("selected");
    else row.classList.remove("selected");
  }

  function syncAllRowSelectedClasses() {
    allBoxes().forEach((b) => {
      const row = b.closest ? b.closest("tr.cap-row") : null;
      if (row) setRowSelectedClass(row, !!b.checked);
    });
  }

  // --- Persist selection across infinite-scroll appends ---
  // Map capture_id -> checked
  const selectedIds = new Set();

  function rememberSelectionFromDom() {
    allBoxes().forEach((b) => {
      const id = (b.value || "").trim();
      if (!id) return;
      if (b.checked) selectedIds.add(id);
      else selectedIds.delete(id);
    });
  }

  function applySelectionToDom() {
    allBoxes().forEach((b) => {
      const id = (b.value || "").trim();
      if (!id) return;
      b.checked = selectedIds.has(id);
    });
    syncAllRowSelectedClasses();
  }

  function updateSelectedUI() {
    // Recompute set from DOM to stay consistent (user may click, shift-click, etc.)
    rememberSelectionFromDom();

    const n = selectedIds.size;

    if (selectedCountEl) {
      selectedCountEl.textContent = String(n);
      selectedCountEl.style.display = n > 0 ? "inline-block" : "none";
    }

    if (clearBtn) {
      clearBtn.style.display = n > 0 ? "inline-flex" : "none";
    }

    if (!selectAll) {
      syncAllRowSelectedClasses();
      return;
    }

    const boxes = allBoxes();
    if (boxes.length === 0) {
      selectAll.checked = false;
      selectAll.indeterminate = false;
      syncAllRowSelectedClasses();
      return;
    }

    if (n === 0) {
      selectAll.checked = false;
      selectAll.indeterminate = false;
    } else if (n === boxes.length) {
      selectAll.checked = true;
      selectAll.indeterminate = false;
    } else {
      selectAll.checked = false;
      selectAll.indeterminate = true;
    }

    syncAllRowSelectedClasses();
  }

  function setRowChecked(row, checked) {
    const cb = row
      ? row.querySelector('input[type="checkbox"][name="capture_ids"]')
      : null;
    if (!cb) return;
    cb.checked = checked;

    const id = (cb.value || "").trim();
    if (!id) return;
    if (checked) selectedIds.add(id);
    else selectedIds.delete(id);
  }

  function setRangeChecked(fromIdx, toIdx, checked) {
    const rows = allRows();
    if (rows.length === 0) return;

    const start = Math.max(0, Math.min(fromIdx, toIdx));
    const end = Math.min(rows.length - 1, Math.max(fromIdx, toIdx));

    for (let i = start; i <= end; i += 1) {
      setRowChecked(rows[i], checked);
    }
  }

  if (selectAll) {
    selectAll.addEventListener("change", () => {
      const on = !!selectAll.checked;
      allBoxes().forEach((b) => {
        b.checked = on;
        const id = (b.value || "").trim();
        if (!id) return;
        if (on) selectedIds.add(id);
        else selectedIds.delete(id);
      });
      selectAll.indeterminate = false;
      updateSelectedUI();
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      selectedIds.clear();
      allBoxes().forEach((b) => (b.checked = false));
      if (selectAll) {
        selectAll.checked = false;
        selectAll.indeterminate = false;
      }
      updateSelectedUI();
    });
  }

  document.addEventListener("change", (ev) => {
    const t = ev.target;
    if (
      t &&
      t.matches &&
      t.matches('input[type="checkbox"][name="capture_ids"]')
    ) {
      const id = (t.value || "").trim();
      if (id) {
        if (t.checked) selectedIds.add(id);
        else selectedIds.delete(id);
      }
      updateSelectedUI();
    }
  });

  function toggleRowSelection(row) {
    if (!row) return;
    const cb = row.querySelector('input[type="checkbox"][name="capture_ids"]');
    if (!cb) return;
    cb.checked = !cb.checked;

    const id = (cb.value || "").trim();
    if (id) {
      if (cb.checked) selectedIds.add(id);
      else selectedIds.delete(id);
    }

    updateSelectedUI();
  }

  function openRow(row) {
    if (!row) return;
    const href = row.getAttribute("data-href");
    if (href) window.location.href = href;
  }

  // --- Prevent annoying "text highlight" while clicking rows ---
  // To select/copy text on purpose: hold Alt and drag (or Alt+click).
  document.addEventListener("mousedown", (ev) => {
    const t = ev.target;
    if (!t) return;

    const row = t.closest ? t.closest("tr.cap-row") : null;
    if (!row) return;

    if (ev.altKey) return;
    if (t.closest && t.closest("a,button,select,textarea,label,input")) return;

    ev.preventDefault();
  });

  // Checkbox clicks (capture phase) for shift-range behavior.
  document.addEventListener(
    "click",
    (ev) => {
      const t = ev.target;
      if (
        !t ||
        !t.matches ||
        !t.matches('input[type="checkbox"][name="capture_ids"]')
      ) {
        return;
      }

      if (suppressClickToggle) return;

      const row = t.closest ? t.closest("tr.cap-row") : null;
      if (!row) return;

      const idx = rowIndex(row);
      if (idx === null) return;

      if (ev.shiftKey && anchorRowIndex !== null) {
        ev.preventDefault();
        const desired = !t.checked;
        setRangeChecked(anchorRowIndex, idx, desired);
        anchorRowIndex = idx;
        updateSelectedUI();
        return;
      }

      window.setTimeout(() => {
        anchorRowIndex = idx;
      }, 0);
    },
    true,
  );

  // Row click toggles selection; shift-click ranges.
  document.addEventListener("click", (ev) => {
    if (suppressClickToggle) return;

    const t = ev.target;
    if (!t) return;

    if (t.closest && t.closest("a,button,select,textarea,label")) return;
    if (t.matches && t.matches('input[type="checkbox"]')) return;

    const row = t.closest ? t.closest("tr.cap-row") : null;
    if (!row) return;

    const idx = rowIndex(row);
    if (idx === null) return;

    if (ev.shiftKey && anchorRowIndex !== null) {
      const cb = row.querySelector(
        'input[type="checkbox"][name="capture_ids"]',
      );
      if (!cb) return;

      const desired = !cb.checked;
      setRangeChecked(anchorRowIndex, idx, desired);
      anchorRowIndex = idx;
      updateSelectedUI();
      return;
    }

    toggleRowSelection(row);
    anchorRowIndex = idx;
  });

  // Double click opens capture.
  document.addEventListener("dblclick", (ev) => {
    const t = ev.target;
    if (!t) return;

    if (t.closest && t.closest("a")) return;

    const row = t.closest ? t.closest("tr.cap-row") : null;
    if (!row) return;

    suppressClickFor(250);
    openRow(row);
  });

  // Keyboard on focused row:
  // Space = toggle, Enter = open
  document.addEventListener("keydown", (ev) => {
    const t = ev.target;
    if (!t) return;

    const row = t.closest ? t.closest("tr.cap-row") : null;
    if (!row) return;

    if (ev.key === " " || ev.key === "Spacebar") {
      ev.preventDefault();
      toggleRowSelection(row);
    } else if (ev.key === "Enter") {
      if (t.closest && t.closest("input,select,textarea,button")) return;
      openRow(row);
    }
  });

  // --- Infinite scroll ---
  if (!tbody || !sentinel || !cfgEl) {
    updateSelectedUI();
    return;
  }

  function readCfg() {
    const base = {};
    const txt = (cfgEl.textContent || "").trim();
    if (txt) {
      try {
        const j = JSON.parse(txt);
        if (j && typeof j === "object") Object.assign(base, j);
      } catch (_) {
        // ignore
      }
    }
    const ds = cfgEl.dataset || {};
    if (ds.apiBase) base.api_base = ds.apiBase;
    if (ds.nextPage) base.next_page = parseInt(ds.nextPage, 10);
    if (ds.pageSize) base.page_size = parseInt(ds.pageSize, 10);
    if (ds.hasMore != null)
      base.has_more = ds.hasMore === "1" || ds.hasMore === "true";
    return base;
  }

  const cfg = readCfg();
  const API_BASE = cfg.api_base || "/api/library/";
  const pageSize = cfg.page_size || 50;

  let nextPage = cfg.next_page || 2;
  let hasMore = !!cfg.has_more;
  let loading = false;

  function show(el, on) {
    if (!el) return;
    el.style.display = on ? "block" : "none";
  }

  function setLoading(on) {
    loading = on;
    show(loadingEl, on);
    show(errorEl, false);
    if (on) show(endEl, false);
  }

  function setEnd() {
    hasMore = false;
    show(loadingEl, false);
    show(errorEl, false);
    show(endEl, true);
  }

  function setError(msg) {
    show(loadingEl, false);
    show(endEl, false);
    if (errorEl) {
      errorEl.textContent = msg || "Error loading more results.";
    }
    show(errorEl, true);
  }

  function currentFilters() {
    const sp = new URLSearchParams(window.location.search);
    const q = (sp.get("q") || "").trim();

    // Prefer collection=, but accept legacy col=
    const collection = (sp.get("collection") || sp.get("col") || "").trim();

    const ps = (sp.get("page_size") || String(pageSize)).trim();
    return { q, collection, page_size: ps };
  }

  function buildApiUrl(page) {
    const f = currentFilters();
    const sp = new URLSearchParams();
    if (f.q) sp.set("q", f.q);
    if (f.collection) sp.set("collection", f.collection);
    sp.set("page", String(page));
    sp.set("page_size", f.page_size || String(pageSize));
    return API_BASE + "?" + sp.toString();
  }

  function appendRows(html) {
    if (!html) return;

    // Remove the "No captures found" row if it exists
    const empty = tbody.querySelector('tr[data-empty="1"]');
    if (empty) empty.remove();

    const tmp = document.createElement("tbody");
    tmp.innerHTML = html;

    // Append + restore selection states for newly added checkboxes
    Array.from(tmp.children).forEach((tr) => tbody.appendChild(tr));
    applySelectionToDom();
    updateSelectedUI();
  }

  async function loadNext() {
    if (loading || !hasMore) return;
    setLoading(true);

    try {
      const url = buildApiUrl(nextPage);
      const res = await fetch(url, {
        headers: { "X-Requested-With": "fetch" },
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();

      if (data && data.rows_html) {
        appendRows(data.rows_html);
      }

      hasMore = !!(data && data.has_more);
      nextPage = data && data.page ? data.page + 1 : nextPage + 1;

      setLoading(false);
      if (!hasMore) setEnd();
    } catch (e) {
      console.error(e);
      setError("Error loading more results.");
      loading = false;
    }
  }

  // Add a simple click-to-retry on the error line
  if (errorEl) {
    errorEl.style.cursor = "pointer";
    errorEl.title = "Click to retry";
    errorEl.addEventListener("click", () => {
      if (!loading && hasMore) loadNext();
    });
  }

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((ent) => {
        if (ent.isIntersecting) loadNext();
      });
    },
    { rootMargin: "200px" },
  );
  io.observe(sentinel);

  // Initial sync (in case server renders checked boxes later)
  updateSelectedUI();
})();
