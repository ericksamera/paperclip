// backend/paperclip/static/captures/library.js
//
// ⚠️ Legacy shim – kept only for backwards compatibility.
//
// The Library UI is now powered by ESM modules under
//   static/captures/library/ (see index.js, state.js, bulk_delete.js, etc.).
//
// This file used to contain a large IIFE that bootstrapped the classic
// library UI. It is no longer referenced by the templates; if something
// loads it directly (old bookmark, custom integration), we keep a safe
// no-op here so nothing breaks mysteriously.
//
// New code should *not* import or modify this file. Prefer the ESM entry
// point: captures/library/index.js

(function () {
  if (window.__pcESMLibraryReady) {
    // ESM bundle already initialized the Library UI.
    return;
  }

  // No-op: see captures/library/index.js for the real implementation.
  if (console && console.warn) {
    console.warn(
      "[paperclip] legacy captures/library.js loaded; " +
        "the ESM-based library under captures/library/ is now the source of truth."
    );
  }
})();
