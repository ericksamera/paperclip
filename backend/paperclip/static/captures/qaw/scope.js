// services/server/paperclip/static/captures/qaw/scope.js
// Mode buttons, year/limit inputs, and “reasoning trace” toggle.

export function initScopeControls({ root }) {
  const yearMin = root.querySelector("#pc-year-min");
  const yearMax = root.querySelector("#pc-year-max");
  const limitEl = root.querySelector("#pc-limit");
  const modeBtns = root.querySelectorAll(".seg__btn");
  const traceToggle = root.querySelector("#pc-trace-toggle");

  const chips = {
    mode: root.querySelector("#pc-mode-chip"),
    limit: root.querySelector("#pc-limit-chip"),
    scope: root.querySelector("#pc-scope-chip"),
  };

  let mode = "hybrid";
  let traceVisible = false;

  // Mode buttons
  modeBtns.forEach((btn) => {
    if (btn.classList.contains("seg__btn--active") && btn.dataset.mode) {
      mode = btn.dataset.mode;
      if (chips.mode) chips.mode.textContent = mode;
    }
  });

  modeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      modeBtns.forEach((b) => b.classList.remove("seg__btn--active"));
      btn.classList.add("seg__btn--active");
      mode = btn.dataset.mode || "hybrid";
      if (chips.mode) chips.mode.textContent = mode;
    });
  });

  function updateChips() {
    if (chips.limit) {
      chips.limit.textContent = String(limitEl?.value || 30);
    }
    const a = (yearMin?.value || "").trim();
    const b = (yearMax?.value || "").trim();
    if (chips.scope) {
      chips.scope.textContent = a || b ? `${a || "—"}–${b || "—"}` : "all years";
    }
  }

  yearMin?.addEventListener("input", updateChips);
  yearMax?.addEventListener("input", updateChips);
  limitEl?.addEventListener("input", updateChips);

  // Reasoning trace toggle
  traceToggle?.addEventListener("click", () => {
    traceVisible = !traceVisible;
    traceToggle.textContent = traceVisible
      ? "Hide reasoning trace"
      : "Show reasoning trace";
    root
      .querySelectorAll(".qaw-trace")
      .forEach((el) => (el.style.display = traceVisible ? "block" : "none"));
  });

  // Initial chip state
  updateChips();

  function parseIntOrNull(input) {
    if (!input) return null;
    const v = parseInt(input.value || "", 10);
    return Number.isFinite(v) ? v : null;
  }

  return {
    getMode() {
      return mode;
    },
    getYearMin() {
      return parseIntOrNull(yearMin);
    },
    getYearMax() {
      return parseIntOrNull(yearMax);
    },
    getLimit() {
      if (!limitEl) return 30;
      const n = parseInt(limitEl.value || "", 10);
      if (!Number.isFinite(n) || !n) return 30;
      return n;
    },
    getTraceVisible() {
      return traceVisible;
    },
    updateChips,
  };
}
