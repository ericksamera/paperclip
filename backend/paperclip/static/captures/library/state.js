// captures/library/state.js
// Minimal shared bag for cross-file UI state (kept tiny on purpose).

export const state = {
  selected: new Set(),   // optional if a page wants it
  pendingDelete: null,   // { ids, flushNow, sent, canceled, cancel } or null
};

// Also expose to classic scripts if needed
if (!window.PCState) window.PCState = state;
