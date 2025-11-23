// backend/paperclip/static/captures/library/self_test.js
// Minimal diagnostics for the Library ESM bundle.
//
// - Shows a small badge with status (ESM booted, selection wired, rows present)
// - Tracks selection events
// - Optionally runs a synthetic click test and then clears selection
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

  // --- Small UI --------------------------------------------------------------

  let root, statusEl, buttonEl, detailEl;

  function ensureUI() {
    if (root) return;

    root = document.createElement("div");
    root.id = "pc-diag";
    root.style.cssText = `
      position: fixed; right: 10px; bottom: 10px; z-index: 2147483647;
      font: 12px/1.3 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
      color: #e5e7eb; background: rgba(15,23,42,0.9);
      border: 1px solid rgba(148,163,184,0.6);
      border-radius: 8px; box-shadow: 0 3px 18px rgba(0,0,0,0.5);
      padding: 8px 10px; width: 260px;
      backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
    `;

    const title = document.createElement("div");
    title.textContent = "Library diagnostics";
    title.style.cssText = "font-weight:600;margin-bottom:6px;";

    statusEl = document.createElement("div");
    statusEl.style.cssText =
      "display:flex;flex-direction:column;gap:3px;margin-bottom:6px;";

    buttonEl = document.createElement("button");
    buttonEl.type = "button";
    buttonEl.textContent = "Run self-test";
    buttonEl.style.cssText =
      "border-radius:6px;border:1px solid rgba(148,163,184,0.7);" +
      "background:#0f172a;color:#e5e7eb;padding:4px 8px;font-size:11px;cursor:pointer;";

    detailEl = document.createElement("div");
    detailEl.style.cssText =
      "margin-top:4px;font-size:11px;opacity:.8;max-height:90px;overflow:auto;";

    buttonEl.addEventListener("click", () => {
      runTests(true);
    });

    root.appendChild(title);
    root.appendChild(statusEl);
    root.appendChild(buttonEl);
    root.appendChild(detailEl);
    document.body.appendChild(root);
  }

  function statusRow(label, ok, hint = "") {
    const line = document.createElement("div");
    line.innerHTML =
      `<span style="opacity:.8">${label}</span> — ` +
      `<b style="color:${ok ? "#7dff9e" : "#ff8c8c"}">${ok ? "OK" : "FAIL"}</b>` +
      (hint ? `<div style="opacity:.7;margin-top:1px">${hint}</div>` : "");
    return line;
  }

  function updateUI() {
    if (!root) return;
    statusEl.textContent = "";

    const { esmBooted, selectionReady, rowsPresent, selectionEventsSeen, clickTest } =
      state;

    statusEl.appendChild(
      statusRow(
        "index.js booted",
        !!esmBooted,
        esmBooted ? "" : "Main entry didn’t mark __pcIndexBooted."
      )
    );
    statusEl.appendChild(
      statusRow(
        "selection wired",
        !!selectionReady,
        selectionReady ? "" : "No pc:selection-change events observed yet."
      )
    );
    statusEl.appendChild(
      statusRow(
        "table/rows present",
        !!rowsPresent,
        rowsPresent ? "" : "Couldn’t find #pc-body rows."
      )
    );
    if (clickTest !== null) {
      statusEl.appendChild(
        statusRow(
          "synthetic click test",
          !!clickTest,
          clickTest ? "" : "Selection wiring didn’t react to synthetic click."
        )
      );
    }

    // Errors / details
    detailEl.textContent = "";
    if (state.errors.length) {
      const ul = document.createElement("ul");
      ul.style.margin = "4px 0 0";
      ul.style.paddingLeft = "16px";
      for (const msg of state.errors.slice(-5)) {
        const li = document.createElement("li");
        li.textContent = String(msg);
        ul.appendChild(li);
      }
      detailEl.appendChild(ul);
    } else {
      detailEl.textContent = "No errors captured.";
    }
  }

  // --- Error capture ---------------------------------------------------------

  window.addEventListener(
    "error",
    (e) => {
      const msg =
        e?.error?.stack || e?.message || (e?.filename || "") + ":" + (e?.lineno || "");
      state.errors.push(String(msg));
      ensureUI();
      updateUI();
    },
    { capture: true }
  );

  window.addEventListener("unhandledrejection", (e) => {
    const msg = e?.reason?.stack || e?.reason || "";
    state.errors.push(String(msg));
    ensureUI();
    updateUI();
  });

  // Keep track of selection events
  document.addEventListener(EVENTS.SELECTION, () => {
    state.selectionEventsSeen += 1;
    state.selectionReady = true;
    ensureUI();
    updateUI();
  });

  // --- Core test runner ------------------------------------------------------

  async function runTests(includeSyntheticClick) {
    ensureUI();

    state.esmBooted = !!(window.__pcIndexBooted || window.__pcESMLibraryReady);
    state.selectionReady = !!(window.__pcSelectionESMReady || window.__pcSelectionESM);
    state.rowsPresent = false;
    state.clickTest = includeSyntheticClick ? null : state.clickTest;

    // Look for a row
    const tb =
      document.getElementById("pc-body") ||
      document.querySelector(".pc-table tbody") ||
      document.querySelector("tbody");
    const tr = tb && (tb.querySelector("tr.pc-row") || tb.querySelector("tr"));
    state.rowsPresent = !!tr;

    updateUI();

    if (!includeSyntheticClick || !tr) return;

    const before = tr.getAttribute("aria-selected") || "false";
    tr.dispatchEvent(
      new MouseEvent("click", { bubbles: true, cancelable: true, view: window })
    );

    setTimeout(async () => {
      const after = tr.getAttribute("aria-selected") || "false";
      state.clickTest = before !== after && after === "true";
      updateUI();

      // Clean up by clearing selection if API is present
      try {
        // Import the canonical feature module (no dependency on legacy selection.js shim)
        const mod = await import("./features/selection.js");
        if (mod?.clearSelection) mod.clearSelection();
      } catch {
        // diagnostics should never break the UI
      }
    }, 60);
  }

  // --- Boot ------------------------------------------------------------------

  document.addEventListener("DOMContentLoaded", () => {
    // Only create UI if the dev explicitly opts in, or if there are errors.
    // Toggle with: localStorage.setItem("pc-diag", "1")
    const WANT =
      typeof localStorage !== "undefined" && localStorage.getItem("pc-diag") === "1";

    if (WANT) {
      ensureUI();
    }

    runTests(false);
  });
})();
