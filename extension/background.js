// Paperclip MV3 background worker (robust).
// - Injects content_script.js on demand if no receiver is present.
// - Handles restricted pages gracefully.
// - Posts to /api/captures/ (note trailing slash).

chrome.runtime.onInstalled.addListener(async () => {
  const defaults = { serverUrl: "http://127.0.0.1:8000" };
  const current = await chrome.storage.sync.get(Object.keys(defaults));
  await chrome.storage.sync.set({ ...defaults, ...current });
  chrome.action.setBadgeBackgroundColor({ color: "#555" });
});

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function sendCaptureMessage(tabId) {
  // Try once; if there's no receiver, inject and try again.
  try {
    return await chrome.tabs.sendMessage(tabId, { type: "paperclip:capture" });
  } catch (err) {
    const msg = String(err && err.message || err || "");
    const noReceiver =
      /Receiving end does not exist|The message port closed before a response/.test(msg);
    if (!noReceiver) throw err;

    // Attempt injection and retry
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["content_script.js"],
      });
      await sleep(50); // let the script register its listener
      return await chrome.tabs.sendMessage(tabId, { type: "paperclip:capture" });
    } catch (injErr) {
      const injMsg = String(injErr && injErr.message || injErr || "");
      // Common on chrome://, chrome-extension://, chrome Web Store, PDFs, etc.
      if (/Cannot access contents of url|Extensions page|chrome:\/\//i.test(injMsg)) {
        throw new Error(
          "Paperclip can’t run on this page (browser-restricted). Open an article on http(s) and try again."
        );
      }
      throw injErr;
    }
  }
}

chrome.action.onClicked.addListener(async () => {
  try {
    const tab = await getActiveTab();
    if (!tab || !tab.id) throw new Error("No active tab.");
    const result = await sendCaptureMessage(tab.id);

    if (!result || !result.ok) {
      throw new Error(result && result.error ? result.error : "Capture failed.");
    }

    const { serverUrl } = await chrome.storage.sync.get({
      serverUrl: "http://127.0.0.1:8000",
    });
    const normalizedBase = (serverUrl || "").replace(/\/+$/, ""); // strip trailing slash

    const body = {
      source_url: result.payload?.meta?.url || result.pageUrl,
      captured_at: new Date().toISOString(),
      dom_html: result.domHTML,
      selection_html: result.selectionHTML || null,
      extraction: {
        meta: result.payload.meta,
        csl: result.payload.csl || {},
        content_html: result.payload.contentHtml,
        references: result.payload.references || [],
        figures: result.payload.figures || [],
        tables: result.payload.tables || []
      },
      rendered: { markdown: result.md, filename: result.filename },
      client: {
        paperclip_version: "0.1.0",
        browser: navigator.userAgent,
        platform: navigator.platform
      }
    };

    // DRF DefaultRouter uses trailing slashes for collection routes.
    const resp = await fetch(`${normalizedBase}/api/captures/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      mode: "cors",
      credentials: "omit"
    });

    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Server error ${resp.status}: ${text}`);
    }
    const json = await resp.json();
    console.log("[Paperclip] Saved:", json);

    chrome.action.setBadgeText({ text: "OK" });
    setTimeout(() => chrome.action.setBadgeText({ text: "" }), 3000);
  } catch (err) {
    console.error("[Paperclip] Error:", err);
    chrome.action.setBadgeText({ text: "ERR" });
    setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
  }
});
