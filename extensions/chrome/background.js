chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;

  // Ask the content script for page data
  let data = null;
  try {
    data = await chrome.tabs.sendMessage(tab.id, { type: "PAPERCLIP_COLLECT" });
  } catch (e) {
    data = null;
  }

  // Fallback: inject a tiny collector if content script didn’t respond
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

  await fetch("http://127.0.0.1:8000/api/captures/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }).catch(() => {});
});
