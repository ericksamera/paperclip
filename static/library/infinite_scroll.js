// static/library/infinite_scroll.js
(function (global) {
  const Paperclip = (global.Paperclip = global.Paperclip || {});
  const ui = () => (Paperclip.ui ? Paperclip.ui : null);
  const selection = () => (Paperclip.selection ? Paperclip.selection : null);

  function init() {
    const tbody = document.getElementById("library-tbody");
    const sentinel = document.getElementById("infinite-sentinel");
    const loadingEl = document.getElementById("infinite-loading");
    const endEl = document.getElementById("infinite-end");
    const errorEl = document.getElementById("infinite-error");
    const cfgEl = document.getElementById("library-config");

    if (!tbody || !sentinel || !cfgEl) return;

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

    function showState(el, on, mode) {
      const u = ui();
      if (u) {
        if (mode === "inline") return u.showInline(el, on);
        if (mode === "flex") return u.showFlex(el, on);
        return u.show(el, on);
      }
      if (!el) return;
      el.style.display = on ? "block" : "none";
    }

    function setLoading(on) {
      loading = on;
      showState(loadingEl, on);
      showState(errorEl, false);
      if (on) showState(endEl, false);
    }

    function setEnd() {
      hasMore = false;
      showState(loadingEl, false);
      showState(errorEl, false);
      showState(endEl, true);
    }

    function setError(msg) {
      showState(loadingEl, false);
      showState(endEl, false);
      if (errorEl) {
        const u = ui();
        if (u) u.setText(errorEl, msg || "Error loading more results.");
        else errorEl.textContent = msg || "Error loading more results.";
      }
      showState(errorEl, true);
    }

    function currentFilters() {
      const sp = new URLSearchParams(window.location.search);
      const q = (sp.get("q") || "").trim();
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

      Array.from(tmp.children).forEach((tr) => tbody.appendChild(tr));

      const sel = selection();
      if (sel && sel.onRowsAppended) sel.onRowsAppended();
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

        if (data && data.rows_html) appendRows(data.rows_html);

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
  }

  Paperclip.infiniteScroll = { init };
})(window);
