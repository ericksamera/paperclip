// Minimal MV3 background service worker.
// Flow:
/// 1) collect URL + DOM + main content + meta
//  2) POST to /api/captures/
//  3) open the capture detail page on success

const API_ENDPOINT = "http://127.0.0.1:8000/api/captures/";
const APP_ORIGIN = new URL(API_ENDPOINT).origin;

const COLORS = { loading: "#5B8DEF", success: "#2E7D32", error: "#C62828" };
const SUCCESS_SHOW_MS = 1000;
const ERROR_SHOW_MS = 1400;

async function setBadge(tabId, { text = "", color = null, title = null }) {
  try {
    await chrome.action.setBadgeText({ tabId, text });
    if (color) await chrome.action.setBadgeBackgroundColor({ tabId, color });
    if (title != null) await chrome.action.setTitle({ tabId, title });
  } catch {
    // tab may be gone
  }
}

async function showLoading(tabId) {
  await setBadge(tabId, { text: "…", color: COLORS.loading, title: "Saving…" });
}
async function showSuccess(tabId) {
  await setBadge(tabId, { text: "✓", color: COLORS.success, title: "Saved" });
  setTimeout(() => setBadge(tabId, { text: "", title: "Save to Paperclip" }), SUCCESS_SHOW_MS);
}
async function showError(tabId) {
  await setBadge(tabId, { text: "!", color: COLORS.error, title: "Save failed" });
  setTimeout(() => setBadge(tabId, { text: "", title: "Save to Paperclip" }), ERROR_SHOW_MS);
}

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.id) return;
  const tabId = tab.id;

  await showLoading(tabId);

  // Ask content script for page data
  let data = null;
  try {
    data = await chrome.tabs.sendMessage(tabId, { type: "PAPERCLIP_COLLECT" });
  } catch (_) {
    data = null;
  }

  // Fallback: tiny collector if content script not available
  if (!data || !data.ok) {
    try {
      const [res] = await chrome.scripting.executeScript({
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

  if (!data || !data.ok) {
    await showError(tabId);
    return;
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
    client: { ext: "chrome", v: chrome.runtime.getManifest().version }
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
    } catch (_) {}

    if (!resp.ok || !captureId) {
      throw new Error(`HTTP ${resp.status}${captureId ? "" : " (no capture_id)"}`);
    }

    await showSuccess(tabId);
    const openUrl = `${APP_ORIGIN}/captures/${captureId}/`;
    chrome.tabs.create({ url: openUrl });
  } catch (e) {
    console.warn("Paperclip capture failed:", e);
    await showError(tabId);
  }
});

chrome.runtime.onInstalled.addListener(() => {
  // Clear any stale badge
  chrome.action.setBadgeText({ text: "" }).catch(() => {});
});
