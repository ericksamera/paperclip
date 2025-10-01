// Tiny toast API: Toast.show(text, { actionText, duration, onAction })
(() => {
  if (window.Toast) return;

  const WRAP = document.createElement('div');
  WRAP.className = 'pc-toast-wrap';
  document.body.appendChild(WRAP);

  function show(text, opts = {}) {
    const { actionText = null, duration = 5000, onAction = null } = opts;

    const el = document.createElement('div');
    el.className = 'pc-toast';
    el.innerHTML = `
      <div class="pc-toast__text">${text}</div>
      <div class="pc-toast__actions">
        ${actionText ? `<button class="pc-toast__btn" data-role="action">${actionText}</button>` : ''}
        <button class="pc-toast__btn" data-role="close" aria-label="Close">Dismiss</button>
      </div>
    `;

    WRAP.appendChild(el);

    let closed = false;
    let t;

    function close() {
      if (closed) return;
      closed = true;
      el.remove();
    }

    if (duration > 0) t = setTimeout(close, duration);

    el.querySelector('[data-role="close"]')?.addEventListener('click', () => {
      if (t) clearTimeout(t);
      close();
    });

    if (actionText) {
      el.querySelector('[data-role="action"]')?.addEventListener('click', () => {
        if (t) clearTimeout(t);
        try {
          if (typeof onAction === 'function') onAction();
        } finally {
          close();
        }
      });
    }

    return { close };
  }

  window.Toast = { show };
})();
