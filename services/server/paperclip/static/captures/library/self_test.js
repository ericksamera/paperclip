// services/server/paperclip/static/captures/library/self_test.js
// Minimal diagnostics for the Library ESM bundle.
// - Shows a small badge with status (ESM booted, selection wired, rows present)
// - Optionally runs a synthetic click test to confirm selection flips and event fires.
// - Never interferes with normal UX; synthetic change is reverted immediately.

import { EVENTS } from "./events.js";

(function () {
  const state = {
    esmBooted: false,
    selectionReady: false,
    rowsPresent: false,
    selectionEventsSeen: 0,
    clickTest: null, // null = not run, true/false = result
    errors: [],
  };

  // --- Error capture (surface parse/runtime errors from other modules)
  window.addEventListener("error", (e) => {
    const msg = e?.error?.stack || e?.message || (e?.filename || "") + ":" + (e?.lineno || "");
    state.errors.push(String(msg));
    update();
  }, { capture: true });

  window.addEventListener("unhandledrejection", (e) => {
    const msg = e?.reason?.stack || e?.reason || "";
    state.errors.push(String(msg));
    update();
  });

  document.addEventListener(EVENTS.SELECTION, () => {
    state.selectionEventsSeen++;
    update();
  });

  // --- Small UI
  let root, statusEl, buttonEl, detailEl;
  function ensureUI() {
    if (root) return;
    root = document.createElement("div");
    root.id = "pc-diag";
    root.style.cssText = `
      position: fixed; right: 10px; bottom: 10px; z-index: 2147483647;
      font: 12px/1.3 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      color: var(--fg, #ddd); background: color-mix(in oklab, var(--panel, #111) 88%, black 12%);
      border: 1px solid color-mix(in oklab, var(--fg, #fff) 10%, transparent);
      border-radius: 8px; box-shadow: 0 3px 18px rgba(0,0,0,.45); padding: 8px 10px; width: 240px;
      backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
    `;

    const title = document.createElement("div");
    title.textContent = "Library diagnostics";
    title.style.cssText = "font-weight:600;margin-bottom:6px;";

    statusEl = document.createElement("div");
    statusEl.style.cssText = "display:flex;gap:8px;align-items:center;margin-bottom:6px;";

    buttonEl = document.createElement("button");
    buttonEl.textContent = "Run click test";
    buttonEl.className = "btn";
    buttonEl.style.cssText = `
      font: inherit; padding: 4px 8px; border-radius: 6px; border: 1px solid #4a4a4a;
      background: #232323; color: #ddd; cursor: pointer;
    `;
    buttonEl.addEventListener("click", async (e) => {
      e.preventDefault();
      await runClickTest();
    });

    detailEl = document.createElement("div");
    detailEl.style.cssText = "margin-top:6px;opacity:.9;";

    const close = document.createElement("a");
    close.href = "#";
    close.textContent = "hide";
    close.style.cssText = "float:right;color:#aaa;text-decoration:none;";
    close.addEventListener("click", (e) => { e.preventDefault(); root.remove(); });

    title.appendChild(close);
    root.appendChild(title);
    root.appendChild(statusEl);
    root.appendChild(buttonEl);
    root.appendChild(detailEl);
    document.body.appendChild(root);
  }

  function color() {
    if (state.errors.length) return "#d33";
    if (!state.esmBooted) return "#d33";
    if (!state.selectionReady || !state.rowsPresent) return "#e69500";
    if (state.clickTest === false) return "#e69500";
    return "#3a7";
  }

  function pill(ok, label) {
    const span = document.createElement("span");
    span.textContent = label;
    span.style.cssText = `
      font-weight: 600; font-size: 11px; padding: 2px 6px; border-radius: 999px;
      background: ${ok ? "rgba(74, 222, 128, .18)" : "rgba(255, 173, 51, .20)"};
      border: 1px solid ${ok ? "rgba(74, 222, 128, .45)" : "rgba(255, 173, 51, .45)"};
    `;
    return span;
  }

  function update() {
    if (!root) return;
    statusEl.innerHTML = "";
    const dot = document.createElement("span");
    dot.style.cssText = `
      display:inline-block;width:10px;height:10px;border-radius:50%;
      background:${color()}; box-shadow: 0 0 0 2px rgba(0,0,0,.25) inset;
    `;
    statusEl.appendChild(dot);

    statusEl.appendChild(pill(state.esmBooted, "ESM"));
    statusEl.appendChild(pill(state.selectionReady, "selection"));
    statusEl.appendChild(pill(state.rowsPresent, "rows"));
    if (state.clickTest !== null) {
      statusEl.appendChild(pill(state.clickTest, "click"));
    }

    const lines = [
      `esmBooted: ${state.esmBooted}`,
      `selectionReady: ${state.selectionReady}`,
      `rowsPresent: ${state.rowsPresent}`,
      `selectionEvents: ${state.selectionEventsSeen}`,
      ...(state.errors.length ? [`errors: ${state.errors.length}`] : []),
    ];
    detailEl.textContent = lines.join("  ·  ");
  }

  function measure() {
    // index.js sets this flag once boot() runs (we add that below)
    state.esmBooted = !!window.__pcIndexBooted;
    // selection.js exposes either of these (current module already sets these) 
    // window.__pcESMSelectionReady and window.pcSelection. :contentReference[oaicite:3]{index=3}
    state.selectionReady = !!(window.__pcESMSelectionReady || window.pcSelection);
    state.rowsPresent = !!document.querySelector("#pc-body tr");
    update();
  }

  async function runClickTest() {
    try {
      const tr = document.querySelector("#pc-body tr.pc-row, #pc-body tr[data-id]");
      if (!tr) {
        state.clickTest = false; update();
        console.warn("[pc-diag] No row to test on.");
        return;
      }
      const before = tr.getAttribute("aria-selected") || "false";

      // Prefer a non-link cell for the test target.
      const target = tr.querySelector("td") || tr;
      const ev = new MouseEvent("click", { bubbles: true, cancelable: true, view: window, button: 0 });
      target.dispatchEvent(ev);
      await new Promise((r) => setTimeout(r, 20));

      const after = tr.getAttribute("aria-selected") || "false";
      const eventSeen = state.selectionEventsSeen > 0;
      state.clickTest = (before !== after) || eventSeen || !!(window.PCState?.selected?.size);

      // Revert visual flip so we don't interfere with the current session
      if (before !== after) tr.setAttribute("aria-selected", before);
      update();

      console.groupCollapsed("pc-diag click test");
      console.log("before:", before, "after:", after, "eventSeen:", eventSeen, "ids:", [...(window.PCState?.selected || [])]);
      console.groupEnd();
    } catch (err) {
      state.errors.push(String(err?.stack || err));
      state.clickTest = false;
      update();
    }
  }

  function boot() {
    ensureUI();
    measure();
    // Auto-run if URL has ?pc-test=1
    const hasParam = new URL(location.href).searchParams.has("pc-test");
    if (hasParam) runClickTest();
    // Observe late table swaps / infinite scroll and keep truth fresh
    const mo = new MutationObserver(() => measure());
    mo.observe(document.body, { childList: true, subtree: true });
    // Expose test to the console
    window.PC_DIAG = { state, runClickTest, measure };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
