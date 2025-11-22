// services/server/paperclip/static/ui/toast.js
// Small toast component (no dependencies). Supports onAction + onClose.
// Keeps the public shape Window.Toast.show(opts) returning { close }.

(function () {
  const cssId = "pc-toast-css";
  if (!document.getElementById(cssId)) {
    const style = document.createElement("style");
    style.id = cssId;
    style.textContent = `
.pc-toast-wrap{position:fixed;right:16px;bottom:16px;display:flex;flex-direction:column;gap:8px;z-index:9999;pointer-events:none}
.pc-toast{background:#222;color:#fff;padding:10px 12px;border-radius:6px;box-shadow:0 4px 20px rgba(0,0,0,.25);display:flex;gap:12px;align-items:center;pointer-events:auto;max-width:480px}
.pc-toast__msg{flex:1;line-height:1.35}
.pc-toast__btn{border:0;background:#fff;color:#222;border-radius:4px;padding:6px 10px;cursor:pointer}
.pc-toast__btn--ghost{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.35)}
`;
    document.head.appendChild(style);
  }

  function ensureWrap() {
    let wrap = document.querySelector(".pc-toast-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "pc-toast-wrap";
      document.body.appendChild(wrap);
    }
    return wrap;
  }

  function show(opts = {}) {
    const {
      message = "",
      actionText = "",
      duration = 3000,
      onAction = null,
      onClose = null,
    } = opts;

    const wrap = ensureWrap();
    const el = document.createElement("div");
    el.className = "pc-toast";
    el.innerHTML = `
      <div class="pc-toast__msg">${message}</div>
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
    let timer = null;

    function close() {
      if (closed) return;
      closed = true;
      try {
        el.remove();
      } catch {}
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

    if (duration && duration > 0) {
      timer = setTimeout(close, duration);
    }

    return { close, __pc_origin: "ui" };
  }

  window.Toast = { show };
})();
