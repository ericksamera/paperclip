// Ask-this-collection controller
import { $, csrfToken, toast } from "./dom.js";

function escapeHtml(s) {
  const d = document.createElement("div");
  d.innerText = s ?? "";
  return d.innerHTML;
}

// Turn bare [12] into anchors linked to #pc-src-12 (or to its dedup group)
function linkifyCitations(html, nToAnchorId) {
  return (html || "").replace(/\[(\d+)\]/g, (_, n) => {
    const id = nToAnchorId[String(n)] || `pc-src-${n}`;
    return `<a class="pc-ask-ref" href="#${id}">[${n}]</a>`;
  });
}

// Very light paragraphs from \n\n blocks
function paragraphs(htmlText) {
  const blocks = (htmlText || "").split(/\n{2,}/);
  return blocks.map(b => `<p>${b.trim()}</p>`).join("");
}

function renderAnswer(outEl, payload) {
  if (payload.error) {
    outEl.innerHTML = `
      <div class="pc-ask__notice pc-ask__notice--error">
        ${escapeHtml(payload.error)}
      </div>`;
    return;
  }

  const answerRaw = payload.answer || "";
  const cites = Array.isArray(payload.citations) ? payload.citations : [];

  // ---- Deduplicate citations by capture id, keep all marker numbers per doc ----
  const byId = new Map();
  for (const c of cites) {
    const key = String(c.id);
    if (!byId.has(key)) byId.set(key, { ...c, ns: [c.n] });
    else byId.get(key).ns.push(c.n);
  }
  // stable order by the smallest marker number in that doc
  const collapsed = Array.from(byId.values()).sort((a, b) => Math.min(...a.ns) - Math.min(...b.ns));

  // Map every [n] -> anchor id for that doc (use the first n in that group)
  const nToAnchorId = {};
  for (const g of collapsed) {
    const anchor = `pc-src-${Math.min(...g.ns)}`;
    for (const n of g.ns) nToAnchorId[String(n)] = anchor;
  }

  // ---- Build answer body (safe → linkified → paragraphized) ----
  const safe = escapeHtml(answerRaw).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const linked = linkifyCitations(safe, nToAnchorId);
  const bodyHtml = paragraphs(linked);

  // ---- Build sources list: “[1,2] Title (Year) • DOI” once per paper ----
  const srcLis = collapsed.map(c => {
    const marks = `[${c.ns.sort((a, b) => a - b).join(",")}]`;
    const metaBits = [];
    if (c.year) metaBits.push(`(${escapeHtml(String(c.year))})`);
    if (c.doi) metaBits.push(`• ${escapeHtml(String(c.doi))}`);
    const tail = metaBits.length ? ` <span class="pc-ask__src-tail">${metaBits.join(" ")}</span>` : "";
    const anchorId = `pc-src-${Math.min(...c.ns)}`;
    return `<li id="${anchorId}"><strong>${marks}</strong> ${escapeHtml(c.title || "")}${tail}</li>`;
  }).join("");

  outEl.innerHTML = `
    <div class="pc-ask__answer">${bodyHtml}</div>
    ${collapsed.length ? `
      <div class="pc-ask__sources">
        <div class="pc-ask__sources-title">Sources</div>
        <ol class="pc-ask__sources-list">${srcLis}</ol>
      </div>` : ""}
  `;
}

export function initCollectionAsk() {
  const card = $("#pc-ask-card");
  if (!card) return;

  const collectionId = card.dataset.collectionId;
  const runBtn  = $("#pc-ask-run");
  const textEl  = $("#pc-ask-text");
  const modeSel = $("#pc-ask-mode");
  const outEl   = $("#pc-ask-output");

  async function ask() {
    const question = (textEl.value || "").trim();
    if (!question) {
      textEl.focus();
      return;
    }

    runBtn.disabled = true;
    outEl.innerHTML = `<div class="pc-ask__notice">Thinking…</div>`;

    try {
      const res = await fetch(`/collections/${encodeURIComponent(collectionId)}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ question, mode: modeSel.value }),
      });
      const payload = await res.json();
      renderAnswer(outEl, payload);
      if (!res.ok && payload?.error) toast(payload.error);
      else if (!res.ok) toast("Ask failed.");
    } catch (err) {
      renderAnswer(outEl, { error: String(err) });
      toast(String(err && err.message ? err.message : "Network error"));
    } finally {
      runBtn.disabled = false;
    }
  }

  runBtn.addEventListener("click", ask);
  textEl.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") ask();
  });
}

// auto-init
document.addEventListener("DOMContentLoaded", initCollectionAsk);
