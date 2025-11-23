// services/server/paperclip/static/captures/library/infra/dom.js
// Canonical DOM + utility helpers used across Library modules.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// Back-compat export names used by some files
export const qs = $;
export const qsa = $$;

export function on(el, ev, fn, opts) {
  if (!el || typeof el.addEventListener !== "function") {
    // Graceful no-op if caller passed something non-DOM
    return () => {};
  }
  el.addEventListener(ev, fn, opts);
  return () => {
    try {
      el.removeEventListener(ev, fn, opts);
    } catch {
      // ignore
    }
  };
}

export function trigger(el, type, detail = {}) {
  el?.dispatchEvent(new CustomEvent(type, { detail, bubbles: true }));
}

// Canonical event names
export const ROWS_CHANGED = "pc:rows-changed";
export const SELECTION = "pc:selection";

// ---- Utilities ---------------------------------------------------------------

export function escapeHtml(s) {
  const d = document.createElement("div");
  d.innerText = s ?? "";
  return d.innerHTML;
}

export function buildQs(next = {}) {
  const u = new URL(location.href);
  for (const [k, v] of Object.entries(next)) {
    if (v === null || v === undefined || v === "") {
      u.searchParams.delete(k);
    } else {
      u.searchParams.set(k, String(v));
    }
  }
  return u.pathname + (u.search ? u.search : "");
}

export function csrfToken() {
  const el = document.querySelector("input[name=csrfmiddlewaretoken]");
  return el?.value || "";
}

// Keep menu/popover on-screen
export function keepOnScreen(el) {
  if (!el || !el.getBoundingClientRect) return;
  const rect = el.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (rect.right > vw) {
    el.style.left = Math.max(8, vw - rect.width - 8) + "px";
  }
  if (rect.bottom > vh) {
    el.style.top = Math.max(8, vh - rect.height - 8) + "px";
  }
}

// Current collection helper (used by menus)
export function currentCollectionId() {
  const active = document.querySelector(".z-left .z-link.active[data-collection-id]");
  return active?.getAttribute("data-collection-id") || null;
}

// Scan collections from left rail
export function scanCollections() {
  const out = [];
  document.querySelectorAll(".z-left .z-link[data-collection-id]").forEach((el) => {
    const id = el.getAttribute("data-collection-id");
    const label = el.querySelector(".z-label")?.textContent?.trim() || "";
    if (id) out.push({ id, label, el });
  });
  return out;
}

// Tiny toast utility; falls back to inline renderer if window.Toast not present
function _miniToast(opts) {
  const {
    message,
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
    boxShadow: "0 4px 20px rgba(0,0,0,0.25)",
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
    btn.onclick = () => {
      try {
        onAction?.();
      } finally {
        close();
      }
    };
    el.appendChild(btn);
  }

  function close() {
    el.remove();
    try {
      onClose?.();
    } catch {
      // ignore
    }
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
  $,
  $$,
  qs,
  qsa,
  on,
  trigger,
  ROWS_CHANGED,
  SELECTION,
  escapeHtml,
  buildQs,
  csrfToken,
  keepOnScreen,
  currentCollectionId,
  scanCollections,
  toast,
});
