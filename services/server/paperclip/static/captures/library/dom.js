// services/server/paperclip/static/captures/library/dom.js
// Canonical DOM + utility helpers used across Library modules.

export const $  = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// Back-compat export names used by some files
export const qs  = $;
export const qsa = $$;

export function on(el, ev, fn, opts) {
  el && el.addEventListener(ev, fn, opts);
  return () => el && el.removeEventListener(ev, fn, opts);
}

export function trigger(el, type, detail = {}) {
  el?.dispatchEvent(new CustomEvent(type, { detail, bubbles: true }));
}

// Canonical event names
export const ROWS_CHANGED = "pc:rows-changed";
export const SELECTION    = "pc:selection";

// ---- Utilities ---------------------------------------------------------------

export function escapeHtml(s) {
  const d = document.createElement("div");
  d.innerText = s ?? "";
  return d.innerHTML;
}

export function buildQs(next = {}) {
  const u = new URL(location.href);
  for (const [k, v] of Object.entries(next)) {
    if (v === null || v === undefined || v === "") u.searchParams.delete(k);
    else u.searchParams.set(k, String(v));
  }
  return u.pathname + (u.search ? u.search : "");
}

export function csrfToken() {
  // Prefer hidden input if present (Django template)
  const inDom = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
  if (inDom) return inDom;
  // Fallback to cookie
  const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export function keepOnScreen(el) {
  try {
    const r = el.getBoundingClientRect();
    const dx = Math.max(0, r.right - (window.innerWidth - 8));
    const dy = Math.max(0, r.bottom - (window.innerHeight - 8));
    if (dx) el.style.left = Math.max(8, r.left - dx) + "px";
    if (dy) el.style.top  = Math.max(8, r.top  - dy) + "px";
  } catch (_) {}
}

export function currentCollectionId() {
  const fromDom = document.querySelector(".z-left .z-link.active[data-collection-id]")?.dataset.collectionId;
  if (fromDom) return fromDom;
  const p = new URL(location.href).searchParams.get("col");
  return p || "all";
}

export function scanCollections() {
  return $$(".z-left .z-link[data-collection-id]").map(a => ({
    id: a.dataset.collectionId,
    label: a.querySelector(".z-label")?.textContent?.trim() || ""
  }));
}

// ---- Toast (fallback if a site-wide Toast isn’t present) ---------------------

function _miniToast(opts = {}) {
  const {
    message = "",
    actionText = "",
    duration = 3000,
    onAction = null,
    onClose = null,
  } = opts;

  let wrap = document.querySelector(".pc-toast-wrap");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.className = "pc-toast-wrap";
    Object.assign(wrap.style, {
      position: "fixed",
      right: "16px",
      bottom: "16px",
      display: "flex",
      flexDirection: "column",
      gap: "8px",
      zIndex: "9999",
      pointerEvents: "none",
    });
    document.body.appendChild(wrap);
  }

  const el = document.createElement("div");
  el.className = "pc-toast";
  Object.assign(el.style, {
    background: "#222",
    color: "#fff",
    padding: "10px 12px",
    borderRadius: "6px",
    boxShadow: "0 4px 20px rgba(0,0,0,.25)",
    display: "flex",
    gap: "12px",
    alignItems: "center",
    pointerEvents: "auto",
    maxWidth: "480px",
    font: "500 13px/1.35 system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
  });
  el.innerHTML = escapeHtml(message);

  if (actionText) {
    const btn = document.createElement("button");
    btn.className = "btn btn--subtle";
    btn.type = "button";
    btn.textContent = actionText;
    btn.onclick = () => { try { onAction?.(); } finally { close(); } };
    el.appendChild(btn);
  }

  function close() {
    el.remove();
    try { onClose?.(); } catch (_) {}
  }

  wrap.appendChild(el);
  const t = setTimeout(close, duration);
  el.addEventListener("mouseenter", () => clearTimeout(t), { once: true });
}

export function toast(opts) {
  if (window.Toast?.show) return window.Toast.show(opts);
  return _miniToast(opts);
}

// Expose a small, stable global for classic scripts (harmless if unused)
if (!window.PCDOM) window.PCDOM = {};
Object.assign(window.PCDOM, {
  $, $$, qs, qsa, on, trigger,
  ROWS_CHANGED, SELECTION,
  escapeHtml, buildQs, csrfToken,
  keepOnScreen, currentCollectionId, scanCollections,
  toast
});
