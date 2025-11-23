// services/server/paperclip/static/captures/qaw/history.js
// Question history sidebar: localStorage + filter + click-to-rerun.

function escapeHtml(s) {
  return String(s ?? "").replace(
    /[&<>\"']/g,
    (m) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[m]
  );
}

export function initHistory({ root, colId, onSelect }) {
  const qList = root.querySelector("#pc-q-list");
  const qFilter = root.querySelector("#pc-q-filter");
  if (!qList || !qFilter || !colId) {
    return {
      add() {},
      isEmpty() {
        return true;
      },
    };
  }

  const KEY = `pc:qaw:${colId}:qs`;

  function loadQs() {
    try {
      const raw = localStorage.getItem(KEY) || "[]";
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function saveQs(list) {
    try {
      localStorage.setItem(KEY, JSON.stringify(list.slice(0, 200)));
    } catch {
      // ignore quota errors etc
    }
  }

  function render() {
    const list = loadQs();
    const filt = (qFilter.value || "").toLowerCase();
    qList.innerHTML = list
      .filter((x) => !filt || x.q.toLowerCase().includes(filt))
      .map(
        (x) => `
        <button class="qaw-q"
                title="${escapeHtml(x.q)}"
                data-q="${encodeURIComponent(x.q)}">
          <div class="qaw-q__title">${escapeHtml(x.q)}</div>
          <div class="qaw-q__meta muted">
            ${escapeHtml(new Date(x.at || Date.now()).toLocaleString())}
          </div>
        </button>`
      )
      .join("");
  }

  qFilter.addEventListener("input", () => render());

  qList.addEventListener("click", (e) => {
    const btn = e.target.closest(".qaw-q");
    if (!btn) return;
    const q = decodeURIComponent(btn.dataset.q || "");
    if (!q) return;
    if (typeof onSelect === "function") onSelect(q);
  });

  // Initial paint
  render();

  return {
    add(question) {
      const q = (question || "").trim();
      if (!q) return;
      const list = loadQs();
      list.unshift({ id: Date.now(), q, at: new Date().toISOString() });
      saveQs(list);
      render();
    },
    isEmpty() {
      return loadQs().length === 0;
    },
  };
}
