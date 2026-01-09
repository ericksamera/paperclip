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

  function updateSelectedUI() {
    const n = selectedCount();

    if (selectedCountEl) {
      if (n > 0) {
        selectedCountEl.style.display = "inline";
        selectedCountEl.textContent = `${n} selected`;
      } else {
        selectedCountEl.style.display = "none";
        selectedCountEl.textContent = "";
      }
    }

    if (clearBtn) {
      clearBtn.style.display = n > 0 ? "inline-flex" : "none";
    }

    if (!selectAll) return;
    const boxes = allBoxes();
    if (boxes.length === 0) {
      selectAll.checked = false;
      selectAll.indeterminate = false;
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
  }

  if (selectAll) {
    selectAll.addEventListener("change", () => {
      const boxes = allBoxes();
      boxes.forEach((b) => (b.checked = selectAll.checked));
      selectAll.indeterminate = false;
      updateSelectedUI();
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
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
      updateSelectedUI();
    }
  });

  // Row click target (ignore interactive elements)
  document.addEventListener("click", (ev) => {
    const t = ev.target;
    if (!t) return;

    if (t.closest && t.closest("a,button,input,select,textarea,label")) return;

    const row = t.closest ? t.closest("tr.cap-row") : null;
    if (!row) return;

    const href = row.getAttribute("data-href");
    if (href) window.location.href = href;
  });

  // --- Infinite scroll ---
  if (!tbody || !sentinel || !cfgEl) {
    updateSelectedUI();
    return;
  }

  const API_BASE = cfgEl.dataset.apiBase || "/api/library/";
  const DETAIL_TMPL = cfgEl.dataset.detailUrlTemplate || "/captures/__CID__/";

  let nextPage = parseInt(cfgEl.dataset.nextPage || "2", 10);
  let pageSize = parseInt(cfgEl.dataset.pageSize || "50", 10);
  let hasMore = cfgEl.dataset.hasMore === "1";
  let loading = false;
  let endShown = false;

  function setLoading(on) {
    if (!loadingEl) return;
    loadingEl.style.display = on ? "block" : "none";
  }

  function showEnd() {
    if (!endEl || endShown) return;
    endEl.style.display = "block";
    endShown = true;
  }

  function showError(msg, onRetry) {
    if (!errorEl) return;
    errorEl.innerHTML = "";
    const span = document.createElement("span");
    span.textContent = msg + " ";
    errorEl.appendChild(span);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn--ghost btn--sm";
    btn.textContent = "Retry";
    btn.addEventListener("click", () => onRetry && onRetry());
    errorEl.appendChild(btn);

    errorEl.style.display = "block";
  }

  function hideError() {
    if (!errorEl) return;
    errorEl.style.display = "none";
    errorEl.textContent = "";
  }

  function currentFilters() {
    const sp = new URLSearchParams(window.location.search);
    const q = (sp.get("q") || "").trim();
    const col = (sp.get("col") || "").trim();
    const ps = (sp.get("page_size") || String(pageSize)).trim();
    return { q, col, page_size: ps };
  }

  function buildApiUrl(page) {
    const f = currentFilters();
    const sp = new URLSearchParams();
    if (f.q) sp.set("q", f.q);
    if (f.col) sp.set("col", f.col);
    sp.set("page", String(page));
    sp.set("page_size", f.page_size || String(pageSize));
    return API_BASE + "?" + sp.toString();
  }

  function captureDetailUrl(id) {
    return DETAIL_TMPL.replace("__CID__", encodeURIComponent(id));
  }

  function removeEmptyRowIfPresent() {
    const emptyRow = tbody.querySelector("tr[data-empty='1']");
    if (emptyRow) emptyRow.remove();
  }

  function appendRow(cap) {
    if (!cap || !cap.id) return;

    removeEmptyRowIfPresent();

    const tr = document.createElement("tr");
    tr.className = "cap-row";
    tr.setAttribute("data-href", captureDetailUrl(cap.id));

    const tdSel = document.createElement("td");
    tdSel.className = "sel";
    const cb = document.createElement("input");
    cb.className = "cap-check";
    cb.type = "checkbox";
    cb.name = "capture_ids";
    cb.value = cap.id;
    if (selectAll && selectAll.checked) cb.checked = true;
    tdSel.appendChild(cb);
    tr.appendChild(tdSel);

    const tdTitle = document.createElement("td");
    tdTitle.className = "title-cell";

    const aTitle = document.createElement("a");
    aTitle.className = "title-link";
    aTitle.href = captureDetailUrl(cap.id);
    aTitle.textContent = cap.title || "Untitled";
    tdTitle.appendChild(aTitle);

    if (cap.abstract_snip) {
      const divAbs = document.createElement("div");
      divAbs.className = "muted small";
      divAbs.textContent = cap.abstract_snip;
      tdTitle.appendChild(divAbs);
    }

    if (cap.url) {
      const divUrl = document.createElement("div");
      divUrl.className = "muted small";
      const aUrl = document.createElement("a");
      aUrl.href = cap.url;
      aUrl.target = "_blank";
      aUrl.rel = "noopener noreferrer";
      aUrl.textContent = cap.url;
      divUrl.appendChild(aUrl);
      tdTitle.appendChild(divUrl);
    }

    tr.appendChild(tdTitle);

    const tdAuthors = document.createElement("td");
    tdAuthors.className = "small";
    tdAuthors.textContent = cap.authors_short || "";
    tr.appendChild(tdAuthors);

    const tdYear = document.createElement("td");
    tdYear.className = "small";
    tdYear.textContent = cap.year || "";
    tr.appendChild(tdYear);

    const tdContainer = document.createElement("td");
    tdContainer.className = "small";
    tdContainer.textContent = cap.container_title || "";
    tr.appendChild(tdContainer);

    const tdDoi = document.createElement("td");
    tdDoi.className = "small";
    tdDoi.textContent = cap.doi || "";
    tr.appendChild(tdDoi);

    tbody.appendChild(tr);
  }

  async function loadNext() {
    if (!hasMore || loading) return;

    loading = true;
    setLoading(true);
    hideError();

    try {
      const resp = await fetch(buildApiUrl(nextPage), {
        headers: { Accept: "application/json" },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const data = await resp.json();
      const caps = data && Array.isArray(data.captures) ? data.captures : [];
      caps.forEach((cap) => appendRow(cap));

      hasMore = !!(data && data.has_more);
      const currentPage =
        data && data.page != null ? Number(data.page) : nextPage;
      nextPage = currentPage + 1;

      if (!hasMore) {
        observer.disconnect();
        showEnd();
      }

      updateSelectedUI();
    } catch (e) {
      console.warn("Infinite scroll fetch failed:", e);
      showError("Couldn’t load more results.", () => loadNext());
    } finally {
      loading = false;
      setLoading(false);
    }
  }

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) loadNext();
      }
    },
    { root: null, rootMargin: "300px 0px", threshold: 0 },
  );

  if (hasMore) observer.observe(sentinel);
  else showEnd();

  updateSelectedUI();
})();
