// Shows a "Saved to Paperclip" desktop notification and a ✓ badge on success.
// Falls back to injecting a tiny collector if the content script doesn't reply.

const API_ENDPOINT = "http://127.0.0.1:8000/api/captures/";
const APP_ORIGIN = new URL(API_ENDPOINT).origin;

let _lastOpenUrl = null;

// --- small helpers ---
function badge(text, color, ms = 1500) {
  chrome.action.setBadgeText({ text });
  if (color) chrome.action.setBadgeBackgroundColor({ color });
  if (ms > 0) setTimeout(() => chrome.action.setBadgeText({ text: "" }), ms);
}

function notifySaved({ title, url, openUrl }) {
  _lastOpenUrl = openUrl || null;
  badge("✓", "#28a745", 1500);

  const message = title || (url ? new URL(url).hostname : "Saved");
  chrome.notifications.create(
    {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "Saved to Paperclip",
      message,
      priority: 1,
      buttons: openUrl ? [{ title: "Open" }] : []
    },
    (id) => setTimeout(() => chrome.notifications.clear(id), 4000)
  );
}

function notifyError(errMessage, pageTitle) {
  badge("!", "#d9534f", 2000);
  chrome.notifications.create(
    {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "Save failed",
      message: (pageTitle ? pageTitle + "\n" : "") + (errMessage || "Unknown error"),
      priority: 2
    },
    (id) => setTimeout(() => chrome.notifications.clear(id), 5000)
  );
}

chrome.notifications.onClicked.addListener(() => {
  if (_lastOpenUrl) chrome.tabs.create({ url: _lastOpenUrl });
});
chrome.notifications.onButtonClicked.addListener((_id, btnIdx) => {
  if (btnIdx === 0 && _lastOpenUrl) chrome.tabs.create({ url: _lastOpenUrl });
});

// --- main capture flow ---
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.id) return;

  // Ask content script for page data
  let data = null;
  try {
    data = await chrome.tabs.sendMessage(tab.id, { type: "PAPERCLIP_COLLECT" });
  } catch (_) {
    data = null;
  }

  // Fallback: tiny collector
  if (!data || !data.ok) {
    const [res] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => ({
        url: location.href,
        dom_html: document.documentElement.outerHTML,
        content_html: document.body ? document.body.innerHTML : "",
        meta: {}
      })
    });
    data = { ok: true, ...res.result };
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
      throw new Error(`HTTP ${resp.status}${captureId ? "" : " (no id)"}`);
    }

    const openUrl = `${APP_ORIGIN}/captures/${captureId}/`;
    const title =
      (payload.extraction.meta && payload.extraction.meta.citation_title) ||
      tab.title ||
      "";

    notifySaved({ title, url: payload.source_url, openUrl });
  } catch (e) {
    notifyError(String(e && e.message ? e.message : e), tab.title || "");
  }
});
