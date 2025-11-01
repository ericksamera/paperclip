// background.js — Firefox MV3 event page
// Shows "…" on badge while saving, then "✓" on success or "!" on error.
// Mirrors your Chrome logic, just using the `browser.*` promise APIs.
// POSTS to the same endpoint you use in Chrome.

const API_ENDPOINT = "http://127.0.0.1:8000/api/captures/";
const APP_ORIGIN = new URL(API_ENDPOINT).origin;

let _lastOpenUrl = null;

/* -------------------------- Badge spinner state -------------------------- */
const COLORS = { loading: "#5B8DEF", success: "#2E7D32", error: "#C62828" };
const MIN_SPIN_MS = 400;     // avoid blink if request is very fast
const SUCCESS_SHOW_MS = 1200;
const ERROR_SHOW_MS = 1500;
const LOADING_GUARD_MS = 15000;

const badgeState = new Map(); // tabId -> { count, loadingSince, clearTimer, guardTimer }

function ensureState(tabId) {
  if (!badgeState.has(tabId)) {
    badgeState.set(tabId, { count: 0, loadingSince: 0, clearTimer: null, guardTimer: null });
  }
  return badgeState.get(tabId);
}
function clearTimers(s) {
  if (s.clearTimer) { clearTimeout(s.clearTimer); s.clearTimer = null; }
  if (s.guardTimer) { clearTimeout(s.guardTimer); s.guardTimer = null; }
}
async function setBadge(tabId, { text = "", color = null, title = null }) {
  try {
    await browser.action.setBadgeText({ tabId, text });
    if (color) await browser.action.setBadgeBackgroundColor({ tabId, color });
    if (title != null) await browser.action.setTitle({ tabId, title });
  } catch { /* tab might be gone */ }
}
async function showLoading(tabId) {
  const s = ensureState(tabId);
  s.count += 1;
  if (s.count === 1) {
    clearTimers(s);
    s.loadingSince = Date.now();
    await setBadge(tabId, { text: "…", color: COLORS.loading, title: "Saving…" });
    // guard against stuck spinner
    s.guardTimer = setTimeout(() => {
      if (s.count > 0) { s.count = 0; clearBadge(tabId); }
    }, LOADING_GUARD_MS);
  }
}
async function showSuccess(tabId) {
  const s = ensureState(tabId);
  s.count = Math.max(0, s.count - 1);
  if (s.count > 0) return; // other in-flight ops still running

  const elapsed = Date.now() - (s.loadingSince || 0);
  const wait = Math.max(0, MIN_SPIN_MS - elapsed);

  clearTimers(s);
  s.clearTimer = setTimeout(async () => {
    await setBadge(tabId, { text: "✓", color: COLORS.success, title: "Saved" });
    s.clearTimer = setTimeout(() => clearBadge(tabId), SUCCESS_SHOW_MS);
  }, wait);
}
async function showError(tabId) {
  const s = ensureState(tabId);
  s.count = Math.max(0, s.count - 1);
  clearTimers(s);
  await setBadge(tabId, { text: "!", color: COLORS.error, title: "Save failed" });
  s.clearTimer = setTimeout(() => clearBadge(tabId), ERROR_SHOW_MS);
}
async function clearBadge(tabId) {
  const s = ensureState(tabId);
  clearTimers(s);
  s.count = 0;
  s.loadingSince = 0;
  await setBadge(tabId, { text: "", title: "" });
}

/* ------------------------------ Notifications --------------------------- */
function notifySaved({ title, url, openUrl }) {
  _lastOpenUrl = openUrl || null; // badge ✓ is handled in showSuccess
  const message = title || (url ? new URL(url).hostname : "Saved");
  (async () => {
    try {
      const id = await browser.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "Saved to Paperclip",
        message,
        priority: 1,
        buttons: openUrl ? [{ title: "Open" }] : []
      });
      setTimeout(() => browser.notifications.clear(id), 4000);
    } catch {}
  })();
}
function notifyError(errMessage, pageTitle) {
  (async () => {
    try {
      const id = await browser.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "Save failed",
        message: (pageTitle ? pageTitle + "\n" : "") + (errMessage || "Unknown error"),
        priority: 2
      });
      setTimeout(() => browser.notifications.clear(id), 5000);
    } catch {}
  })();
}
browser.notifications.onClicked.addListener(() => {
  if (_lastOpenUrl) browser.tabs.create({ url: _lastOpenUrl });
});
browser.notifications.onButtonClicked.addListener((_id, btnIdx) => {
  if (btnIdx === 0 && _lastOpenUrl) browser.tabs.create({ url: _lastOpenUrl });
});

/* --------------------------------- Main ---------------------------------- */
browser.action.onClicked.addListener(async (tab) => {
  if (!tab || !tab.id) return;
  const tabId = tab.id;

  await showLoading(tabId);

  // Ask content script for page data
  let data = null;
  try {
    data = await browser.tabs.sendMessage(tabId, { type: "PAPERCLIP_COLLECT" });
  } catch (_) {
    data = null;
  }

  // Fallback: tiny collector if content script not available or host perms not granted
  if (!data || !data.ok) {
    try {
      const [res] = await browser.scripting.executeScript({
        target: { tabId },
        func: () => ({
          url: location.href,
          dom_html: document.documentElement.outerHTML,
          content_html: document.body ? document.body.innerHTML : "",
          meta: {}
        })
      });
      data = { ok: true, ...res.result };
    } catch (e) {
      data = { ok: false, error: String(e) };
    }
  }

  const payload = {
    source_url: data.url,
    dom_html: data.dom_html,
    extraction: {
      meta: data.meta || {},
      content_html: data.content_html || "",
      references: []
    },
    rendered: {},
    client: { ext: "firefox", v: browser.runtime.getManifest().version }
  };

  try {
    const resp = await fetch(API_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    let captureId = null;
    try {
      const j = await resp.json();
      captureId = j && j.capture_id;
    } catch {}

    if (!resp.ok || !captureId) {
      throw new Error(`HTTP ${resp.status}${captureId ? "" : " (no id)"}`);
    }

    const openUrl = `${APP_ORIGIN}/captures/${captureId}/`;
    const title =
      (payload.extraction.meta && payload.extraction.meta.citation_title) ||
      tab.title || "";

    await showSuccess(tabId);
    notifySaved({ title, url: payload.source_url, openUrl });
  } catch (e) {
    await showError(tabId);
    notifyError(String(e && e.message ? e.message : e), tab.title || "");
  }
});

/* ------------------------------ Install hook ----------------------------- */
browser.runtime.onInstalled.addListener(() => {
  browser.action.setBadgeText({ text: "" }).catch(() => {});
});
