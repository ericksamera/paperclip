// services/server/paperclip/static/captures/imports.js
import { toast } from "./library/dom.js"; // re-use same toast; path matches your ESM tree

const DOI_RE = /\b10\.\d{4,9}\/\S+\b/i;

function extractDois(t) {
  const out = new Set();
  (t || "").replace(/\s+/g, " ").split(/[,\s]+/).forEach((tok) => {
    if (DOI_RE.test(tok)) out.add(tok.match(DOI_RE)[0]);
  });
  // Also scan full text for DOIs embedded in prose
  const inText = (t || "").match(new RegExp(DOI_RE, "gi")) || [];
  inText.forEach((d) => out.add(d));
  return Array.from(out);
}

function renderResult(el, data) {
  if (!el) return;
  el.style.display = "block";
  const { count = {}, created = [], existing = [], errors = [] } = data || {};
  el.innerHTML = `
    <div><b>Imported</b>: ${count.created || 0} new, ${count.existing || 0} existing.</div>
    ${
      errors.length
        ? `<div style="color:var(--danger)">${errors.length} error(s).</div>`
        : ``
    }
    <div style="margin-top:8px">
      <a class="btn" href="/library/">Go to Library</a>
    </div>`;
}

(function boot() {
  const doiForm = document.getElementById("pc-doi-form");
  const doiText = document.getElementById("pc-doi-text");
  const doiCount = document.getElementById("pc-doi-count");
  const risForm = document.getElementById("pc-ris-form");
  const drop = document.getElementById("pc-drop");
  const fileInput = document.getElementById("pc-ris-input");
  const risName = document.getElementById("pc-ris-name");
  const result = document.getElementById("pc-import-result");

  if (doiText && doiCount) {
    const updateCount = () => {
      const n = extractDois(doiText.value).length;
      doiCount.textContent = n ? `${n} DOI${n > 1 ? "s" : ""} detected` : "";
    };
    doiText.addEventListener("input", updateCount);
    updateCount();
  }

  if (doiForm) {
    doiForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = e.currentTarget;
      const fd = new FormData(form);
      const resp = await fetch(form.action, {
        method: "POST",
        body: fd,
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!resp.ok) {
        toast("Import failed. Try again.");
        return;
      }
      const data = await resp.json();
      renderResult(result, data);
      toast(`Imported ${data?.count?.created || 0} new, ${data?.count?.existing || 0} existing.`);
    });
  }

  if (drop && fileInput) {
    const pick = () => fileInput.click();
    drop.addEventListener("click", pick);
    drop.addEventListener("dragover", (e) => {
      e.preventDefault();
      drop.style.background = "color-mix(in oklab, var(--panel) 85%, var(--fg) 15%)";
    });
    drop.addEventListener("dragleave", () => {
      drop.style.background = "";
    });
    drop.addEventListener("drop", (e) => {
      e.preventDefault();
      drop.style.background = "";
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) {
        fileInput.files = e.dataTransfer.files;
        risName.textContent = f.name;
      }
    });
    fileInput.addEventListener("change", () => {
      const f = fileInput.files && fileInput.files[0];
      risName.textContent = f ? f.name : "";
    });
  }

  if (risForm) {
    risForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = e.currentTarget;
      const fd = new FormData(form);
      const resp = await fetch(form.action, {
        method: "POST",
        body: fd,
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!resp.ok) {
        toast("Import failed. Try again.");
        return;
      }
      const data = await resp.json();
      renderResult(result, data);
      toast(`Imported ${data?.count?.created || 0} new from file.`);
    });
  }
})();
