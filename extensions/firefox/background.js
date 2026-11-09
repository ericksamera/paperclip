// Firefox MV3 uses a background event page (background.scripts), not a service worker.
// The article collector runs only after the user clicks the toolbar button.
const API_ENDPOINT = "http://127.0.0.1:8000/api/captures/";
const APP_ORIGIN = new URL(API_ENDPOINT).origin;
const OPEN_CAPTURE_AFTER_SAVE = false;

const COLORS = { loading: "#5B8DEF", success: "#2E7D32", error: "#C62828" };
const SUCCESS_SHOW_MS = 1000;
const ERROR_SHOW_MS = 1800;

// Injected functions must be self-contained: they cannot use background globals.
function collectPage() {
  function pick(selectorList) {
    for (const sel of selectorList) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  const wanted = new Set([
    "citation_title",
    "citation_doi",
    "citation_publication_date",
    "citation_journal_title",
    "citation_keywords",
    "citation_author",
    "citation_authors",
    "dc.title",
    "dc.identifier",
    "dc.date",
    "dc.creator",
    "dcterms.title",
    "dcterms.issued",
    "prism.title",
    "prism.doi",
    "prism.publicationname",
    "prism.publicationdate",
    "citation_date",
    "keywords",
  ]);

  const meta = {};
  document.querySelectorAll("meta[name],meta[property]").forEach((m) => {
    const name = (m.getAttribute("name") || m.getAttribute("property") || "")
      .toLowerCase();
    if (!wanted.has(name)) return;
    const value = m.getAttribute("content");
    if (!value) return;

    if (meta[name] == null) meta[name] = value;
    else if (Array.isArray(meta[name])) meta[name].push(value);
    else meta[name] = [meta[name], value];
  });

  const main = pick([
    "article",
    "main",
    "[role='main']",
    ".article-body",
    ".articleBody",
    ".ArticleBody",
    "#content",
    ".content",
    ".main-content",
    "#main-content",
    ".post",
    ".entry-content",
  ]);
  const content =
    main && main.innerHTML && (main.innerText || "").trim().length > 60
      ? main
      : document.body;

  return {
    url: location.href,
    dom_html: document.documentElement?.outerHTML || "",
    content_html: content?.innerHTML || "",
    meta,
  };
}

async function setBadge(tabId, { text = "", color = null, title = null }) {
  try {
    await browser.action.setBadgeText({ tabId, text });
    if (color) await browser.action.setBadgeBackgroundColor({ tabId, color });
    if (title != null) await browser.action.setTitle({ tabId, title });
  } catch {
    // Tab may have closed.
  }
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

async function captureTab(tab) {
  const tabId = tab?.id;
  if (!Number.isInteger(tabId)) return;

  await setBadge(tabId, { text: "…", color: COLORS.loading, title: "Saving…" });

  try {
    const injected = await browser.scripting.executeScript({
      target: { tabId },
      func: collectPage,
    });
    const page = injected?.[0]?.result;
    if (!page?.url) throw new Error("Cannot collect this page");

    const payload = {
      source_url: page.url,
      dom_html: page.dom_html,
      extraction: {
        meta: page.meta || {},
        content_html: page.content_html || "",
        references: [],
      },
      rendered: {},
      client: { ext: "firefox", v: browser.runtime.getManifest().version },
    };

    const resp = await fetch(API_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const headerRid = resp.headers.get("X-Request-ID");
    let body = null;
    try {
      body = await resp.json();
    } catch {
      // Bad response is reported below.
    }
    const bodyRid =
      typeof body?.error?.request_id === "string"
        ? body.error.request_id
        : null;
    const requestId = headerRid || bodyRid || null;
    const captureId = body?.capture_id;

    if (!resp.ok || !captureId) {
      const error = new Error(`HTTP ${resp.status} (request_id=${requestId || "unknown"})`);
      error.request_id = requestId;
      throw error;
    }

    await showSuccess(tabId);
    if (OPEN_CAPTURE_AFTER_SAVE) {
      await browser.tabs.create({
        url: `${APP_ORIGIN}/captures/${encodeURIComponent(captureId)}/`,
      });
    }
  } catch (error) {
    console.warn("Paperclip capture failed:", error);
    await showError(tabId, error?.request_id || null);
  }
}

browser.action.onClicked.addListener(captureTab);
