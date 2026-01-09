// Minimal MV3 background service worker.
// Flow:
//  1) collect URL + DOM + main content + meta
//  2) POST to /api/captures/
//  3) open the capture detail page on success

const API_ENDPOINT = "http://127.0.0.1:8000/api/captures/";
const APP_ORIGIN = new URL(API_ENDPOINT).origin;

const COLORS = { loading: "#5B8DEF", success: "#2E7D32", error: "#C62828" };
const SUCCESS_SHOW_MS = 1000;
const ERROR_SHOW_MS = 1800;

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
  setTimeout(
    () => setBadge(tabId, { text: "", title: "Save to Paperclip" }),
    SUCCESS_SHOW_MS,
  );
}
async function showError(tabId, requestId = null) {
  const title = requestId ? `Save failed (${requestId})` : "Save failed";
  await setBadge(tabId, { text: "!", color: COLORS.error, title });
  setTimeout(
    () => setBadge(tabId, { text: "", title: "Save to Paperclip" }),
    ERROR_SHOW_MS,
  );
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
          meta: {},
        }),
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
      references: [],
    },
    rendered: {},
    client: { ext: "chrome", v: chrome.runtime.getManifest().version },
  };

  try {
    const resp = await fetch(API_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const headerRid = resp.headers.get("X-Request-ID");

    let j = null;
    try {
      j = await resp.json();
    } catch (_) {
      j = null;
    }

    const bodyRid =
      j && j.error && typeof j.error.request_id === "string"
        ? j.error.request_id
        : null;

    const requestId = headerRid || bodyRid || null;
    const captureId = j && j.capture_id ? j.capture_id : null;

    if (!resp.ok || !captureId) {
      const msg = `HTTP ${resp.status}${captureId ? "" : " (no capture_id)"}${
        requestId ? ` (request_id=${requestId})` : ""
      }`;
      const err = new Error(msg);
      err.request_id = requestId;
      err.http_status = resp.status;
      err.response_json = j;
      throw err;
    }

    await showSuccess(tabId);
    const openUrl = `${APP_ORIGIN}/captures/${captureId}/`;
    chrome.tabs.create({ url: openUrl });
  } catch (e) {
    const rid = e && e.request_id ? e.request_id : null;
    if (rid) {
      console.warn("Paperclip capture failed:", e, { request_id: rid });
    } else {
      console.warn("Paperclip capture failed:", e);
    }
    await showError(tabId, rid);
  }
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.action.setBadgeText({ text: "" }).catch(() => {});
});
