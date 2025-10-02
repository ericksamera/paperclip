/* services/server/paperclip/static/captures/library/dom.js */
// One place for tiny DOM utils + UX helpers used across the Library UI.
// Export as ESM and also attach to window (so classic scripts can use it).

/* ------------------------- DOM shorthands ------------------------- */
export function $(sel, root = document) { return root.querySelector(sel); }
export function $$(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }
export function on(target, event, handler, opts) {
  target?.addEventListener?.(event, handler, opts);
  return () => target?.removeEventListener?.(event, handler, opts);
}

/* ------------------------- Querystring helper -------------------- */
export function buildQs(next) {
  const u = new URL(location.href);
  const p = u.searchParams;
  Object.keys(next || {}).forEach((k) => {
    const v = next[k];
    if (v === null || v === undefined || v === "") p.delete(k);
    else p.set(k, String(v));
  });
  if (!("page" in (next || {}))) p.delete("page");
  return "?" + p.toString();
}

/* ------------------------- CSRF helpers -------------------------- */
function _cookie(name) {
  const m = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[2]) : "";
}
export function csrfToken() {
  return (
    _cookie("csrftoken") ||
    document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    ""
  );
}

/* ------------------------- HTML escape --------------------------- */
export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[m]));
}

/* ------------------------- Keep a popup on screen ---------------- */
export function keepOnScreen(el, margin = 8) {
  if (!el) return;
  const r = el.getBoundingClientRect();
  let nx = r.left, ny = r.top;
  if (r.right > innerWidth)   nx = Math.max(margin, innerWidth  - r.width  - margin);
  if (r.bottom > innerHeight) ny = Math.max(margin, innerHeight - r.height - margin);
  if (nx !== r.left) el.style.left = nx + "px";
  if (ny !== r.top)  el.style.top  = ny + "px";
}

/* ------------------------- Toast (fallback) ---------------------- */
export function toast(message, { duration = 3000, actionText = "", onAction = null } = {}) {
  // Prefer global Toast if present
  if (typeof window.Toast?.show === "function") {
    window.Toast.show(message, actionText ? { actionText, duration, onAction } : { duration });
    return { close() {} };
  }
  // Tiny fallback
  let host = document.getElementById("pc-toast-host");
  if (!host) {
    host = document.createElement("div");
    host.id = "pc-toast-host";
    host.style.cssText = "position:fixed;left:12px;bottom:12px;z-index:99999;display:flex;flex-direction:column;gap:8px";
    document.body.appendChild(host);
  }
  const card = document.createElement("div");
  card.style.cssText = "max-width:520px;background:rgba(28,32,38,0.98);color:#e6edf3;border:1px solid #2e3640;border-radius:10px;padding:10px 12px;display:flex;align-items:center;gap:10px;box-shadow:0 8px 24px rgba(0,0,0,0.35)";
  card.textContent = message;
  if (actionText) {
    const btn = document.createElement("button");
    btn.textContent = actionText;
    btn.style.cssText = "border:0;background:transparent;color:#8ab4ff;cursor:pointer";
    btn.onclick = () => { try { onAction?.(); } finally { close(); } };
    card.appendChild(btn);
  }
  host.appendChild(card);
  const t = setTimeout(close, duration);
  function close(){ clearTimeout(t); card.remove(); }
  return { close };
}

/* ------------------------- Library helpers ----------------------- */
export function currentCollectionId() {
  const p = new URL(location.href).searchParams;
  return (p.get("col") || "").trim();
}

/** Find collections in the left rail (id + label + anchor element) */
export function scanCollections() {
  const zLeft = document.getElementById("z-left");
  if (!zLeft) return [];
  const links = [...zLeft.querySelectorAll("[data-collection-id], a[href*='col='], a[href^='/collections/']")];
  const list = [];
  links.forEach(a => {
    let id = a.getAttribute("data-collection-id");
    if (!id) {
      try {
        const href = a.getAttribute("href") || "";
        if (href.includes("col=")) {
          const u = new URL(href, location.href);
          id = u.searchParams.get("col");
        } else {
          const m = href.match(/\/collections\/([^/?#]+)/);
          if (m) id = m[1];
        }
      } catch {}
    }
    const label = (a.querySelector(".z-label")?.textContent || a.textContent || "").trim();
    if (id && label && !/^(All items|New collection)$/i.test(label)) {
      a.dataset.collectionId = id;
      list.push({ id, label, el: a });
    }
  });
  return list;
}

/* ------------------------- Global bridge ------------------------- */
// Classic scripts (like captures/library.js) can use window.PCDOM.*
window.PCDOM = Object.freeze({
  $, $$, on,
  buildQs, csrfToken, escapeHtml, keepOnScreen, toast,
  currentCollectionId, scanCollections,
});
window.Toast = window.Toast || { show: (message, opts) => toast(message, opts) };
