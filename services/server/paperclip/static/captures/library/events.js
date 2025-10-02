// services/server/paperclip/static/captures/library/events.js
// Canonical, central event helpers for Library UI.

export const EVENTS = Object.freeze({
  ROWS_CHANGED:  "pc:rows-changed",
  ROWS_UPDATED:  "pc:rows-updated",   // legacy
  ROWS_REPLACED: "pc:rows-replaced",  // legacy
  SELECTION:     "pc:selection-change",
});

export function emitRowsChanged(detail) {
  document.dispatchEvent(new CustomEvent(EVENTS.ROWS_CHANGED, { detail }));
}

export function onRowsChanged(handler, opts) {
  document.addEventListener(EVENTS.ROWS_CHANGED, handler, opts);
  return () => document.removeEventListener(EVENTS.ROWS_CHANGED, handler, opts);
}

// Idempotent legacy bridge: re-emit canonical event when older events fire.
(function wireLegacyOnce(){
  if (window.__pcRowsEventsWired) return;
  window.__pcRowsEventsWired = true;

  const reemit = (e) => emitRowsChanged(e.detail);
  document.addEventListener(EVENTS.ROWS_UPDATED,  reemit, { capture: true });
  document.addEventListener(EVENTS.ROWS_REPLACED, reemit, { capture: true });
})();
