// services/server/paperclip/static/captures/library/dom.js
// Canonical DOM/event helpers used across Library modules.

export function qs(sel, root = document) {
  return root.querySelector(sel);
}

export function qsa(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}

export function on(el, ev, fn, opts) {
  el.addEventListener(ev, fn, opts);
  return () => el.removeEventListener(ev, fn, opts);
}

export function trigger(el, type, detail = {}) {
  el.dispatchEvent(new CustomEvent(type, { detail, bubbles: true }));
}

export const ROWS_CHANGED = "pc:rows-changed";
export const SELECTION = "pc:selection";

// Mini toast fallback if Window.Toast is not present.
// Supports { message, actionText, duration, onAction, onClose }.
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
  });
  el.innerHTML = `
    <div class="pc-toast__msg" style="flex:1;line-height:1.35">${message}</div>
    ${
      actionText
        ? `<button class="pc-toast__btn">${actionText}</button>`
        : ""
    }
    <button class="pc-toast__btn pc-toast__btn--ghost" title="Dismiss">×</button>
  `;
  wrap.appendChild(el);

  const btnAction = actionText ? el.querySelector(".pc-toast__btn") : null;
  const btnClose = el.querySelector(".pc-toast__btn--ghost");

  let closed = false;
  function close() {
    if (closed) return;
    closed = true;
    el.remove();
    if (typeof onClose === "function") {
      try {
        onClose();
      } catch {}
    }
  }

  if (btnAction) {
    btnAction.addEventListener("click", () => {
      if (typeof onAction === "function") {
        try {
          onAction();
        } catch {}
      }
      close();
    });
  }
  btnClose.addEventListener("click", close);

  const t = duration && duration > 0 ? setTimeout(close, duration) : null;
  return { close, __pc_origin: "mini", _t: t };
}

export function toast(opts = {}) {
  const show = window.Toast?.show || _miniToast;
  return show(opts);
}
