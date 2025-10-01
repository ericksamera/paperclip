// DOM helpers shared across modules
export const $  = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
export const on = (el, ev, fn, opts) => el && el.addEventListener(ev, fn, opts);

export function getCookie(name) {
  const m = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[2]) : "";
}
export function csrfToken() {
  return getCookie("csrftoken") || ($("input[name=csrfmiddlewaretoken]")?.value || "");
}
export function escapeHtml(s = "") {
  return String(s).replace(/[&<>"']/g, m => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[m]));
}

export function urlParamsObj() {
  const u = new URL(location.href);
  const o = {};
  u.searchParams.forEach((v, k) => { if (v !== "") o[k] = v; });
  return o;
}
export function buildQs(updates) {
  const u = new URL(location.href);
  const p = u.searchParams;
  Object.keys(updates).forEach(k => {
    const v = updates[k];
    if (v === null || v === undefined) p.delete(k);
    else p.set(k, String(v));
  });
  if (!("page" in updates)) p.delete("page");
  return "?" + p.toString();
}
export function pushUrl(newQs) {
  try { history.replaceState({}, "", newQs); } catch (_) {}
}
export function toast(text, opts = {}) {
  return window.Toast?.show?.(text, opts);
}
