// services/server/paperclip/static/captures/qaw/index.js
// Entry point for the Q&A workspace.
//
// Responsibilities:
//   • Discover the root element (#pc-qaw)
//   • Wire feature modules: history, scope, ask
//   • Ensure we only boot once even if called twice (shim + direct import)

import { initHistory } from "./history.js";
import { initScopeControls } from "./scope.js";
import { initAskForm } from "./ask.js";

let booted = false;

export function initQaw(root) {
  if (booted) return;
  booted = true;

  const shell = root || document.getElementById("pc-qaw");
  if (!shell) return;

  const colId = shell.dataset.colId || "";
  const postUrl = shell.dataset.postUrl || "";
  if (!postUrl) return;

  // Scope controls (mode, year range, limit, trace toggle)
  const scope = initScopeControls({ root: shell });

  // History sidebar (localStorage + list UI)
  let askApi = null;

  const history = initHistory({
    root: shell,
    colId,
    onSelect(question) {
      if (askApi && typeof askApi.runWithQuestion === "function") {
        askApi.runWithQuestion(question);
      }
    },
  });

  // Ask bar + answer renderer
  askApi = initAskForm({
    root: shell,
    postUrl,
    history,
    scope,
  });
}

// Auto-boot on load (safe even if qaw.js shim also calls initQaw)
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => initQaw());
} else {
  initQaw();
}
