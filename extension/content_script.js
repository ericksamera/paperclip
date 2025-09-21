// Runs on every page; waits for background to ask for a capture.

function getSelectionHTML() {
  const sel = window.getSelection && window.getSelection();
  if (!sel || sel.isCollapsed) return null;
  const range = sel.getRangeAt(0).cloneContents();
  const div = document.createElement("div");
  div.appendChild(range);
  return div.innerHTML;
}

function elemHasManyParagraphs(el) {
  try { return (el.querySelectorAll("p").length || 0); } catch { return 0; }
}

// Heuristic main content: prefer <article>, then <main>/<role=main>, else the element with most <p>s.
function findMainElement() {
  const article = document.querySelector("article");
  if (article) return article;
  const main = document.querySelector("main, [role=main]");
  if (main) return main;

  const candidates = new Set([
    ...document.querySelectorAll("article, main, [role=main], .article, .post, .entry-content, #content"),
    document.body
  ]);
  let best = document.body, bestScore = -1;
  candidates.forEach(el => {
    const score = elemHasManyParagraphs(el);
    if (score > bestScore) { best = el; bestScore = score; }
  });
  return best || document.body;
}

function collectReferences(root) {
  const out = [];
  const doiRe = /\b10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+\b/;
  // Try heading "References/Bibliography/Works Cited"
  const headers = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")];
  let refBlock = null;
  for (const h of headers) {
    if (/(references|bibliography|works cited)/i.test(h.textContent || "")) {
      // Find the next list block
      let sib = h.nextElementSibling;
      while (sib && !/^(OL|UL|DIV|SECTION)$/i.test(sib.tagName)) sib = sib.nextElementSibling;
      if (sib) { refBlock = sib; break; }
    }
  }
  if (!refBlock) {
    refBlock = document.querySelector("ol.references, ul.references, #references ol, #references ul, .references ol, .references ul");
  }
  const items = refBlock ? [...refBlock.querySelectorAll("li")] : [];
  items.forEach((li, i) => {
    const raw = (li.innerText || "").trim();
    if (!raw) return;
    const m = raw.match(doiRe);
    out.push({
      id: `ref-${i + 1}`,
      raw,
      doi: m ? m[0] : null,
      bibtex: null,
      apa: raw,       // naive placeholder; your server stores it verbatim
      csl: {}         // optional in v1
    });
  });
  return out;
}

function collectFigures(root) {
  const out = [];
  const figures = [...root.querySelectorAll("figure")];
  figures.forEach((fig, i) => {
    const img = fig.querySelector("img");
    const cap = fig.querySelector("figcaption");
    out.push({
      label: `Figure ${i + 1}`,
      caption: cap ? cap.innerText.trim() : (img && img.alt) || null,
      src: img ? img.src : null
    });
  });
  return out;
}

function collectTables(root) {
  const out = [];
  const tables = [...root.querySelectorAll("table")];
  tables.forEach((t, i) => {
    const cap = t.querySelector("caption");
    out.push({
      label: `Table ${i + 1}`,
      caption: cap ? cap.innerText.trim() : null,
      html: t.outerHTML
    });
  });
  return out;
}

// Extremely simple HTML->Markdown (good enough for proof-of-parse)
function toMarkdown(html) {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;

  function textify(node) {
    if (node.nodeType === Node.TEXT_NODE) return node.nodeValue;
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const tag = node.tagName.toLowerCase();
    const children = [...node.childNodes].map(textify).join("");

    if (tag === "h1") return `# ${children}\n\n`;
    if (tag === "h2") return `## ${children}\n\n`;
    if (tag === "h3") return `### ${children}\n\n`;
    if (tag === "p") return `${children}\n\n`;
    if (tag === "em" || tag === "i") return `*${children}*`;
    if (tag === "strong" || tag === "b") return `**${children}**`;
    if (tag === "a") return `[${children}](${node.getAttribute("href") || ""})`;
    if (tag === "li") return `- ${children}\n`;
    if (tag === "ul" || tag === "ol") return `${children}\n`;
    if (tag === "br") return `\n`;
    if (tag === "img") return `![${node.getAttribute("alt") || ""}](${node.getAttribute("src") || ""})`;
    return children;
  }
  return textify(tmp).trim() + "\n";
}

async function doCapture() {
  const domHTML = document.documentElement ? document.documentElement.outerHTML : "";
  const main = findMainElement();
  const contentHtml = main ? main.outerHTML : (document.body ? document.body.outerHTML : domHTML);
  const selectionHTML = getSelectionHTML();

  const references = collectReferences(main || document);
  const figures = collectFigures(main || document);
  const tables = collectTables(main || document);

  const title = document.title || "";
  const md = `---\nsource_url: ${location.href}\n---\n\n# ${title}\n\n` + toMarkdown(contentHtml);
  const safeTitle = title.replace(/[^\w\d]+/g, "_").slice(0, 60) || "paperclip_capture";
  const filename = `${safeTitle}.md`;

  const payload = {
    meta: {
      title,
      doi: null,
      pmid: null,
      pmcid: null,
      journal: null,
      source: "Generic",   // as per design doc; adapters can set specific sources later
      url: location.href
    },
    csl: {},
    contentHtml,    // local naming; background maps to content_html
    references,
    figures,
    tables
  };

  return {
    ok: true,
    pageUrl: location.href,
    domHTML,
    selectionHTML,
    md,
    filename,
    payload
  };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "paperclip:capture") {
    (async () => {
      try {
        const result = await doCapture();
        sendResponse(result);
      } catch (e) {
        sendResponse({ ok: false, error: e && e.message || String(e) });
      }
    })();
    return true; // keep the message channel open for async sendResponse
  }
});
