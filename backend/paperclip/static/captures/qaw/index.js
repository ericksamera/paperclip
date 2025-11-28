// services/server/paperclip/static/captures/qaw/index.js
// Entry point for the Q&A workspace.
//
// Responsibilities:
//   • Discover the root element (#pc-qaw)
//   • Wire feature modules: history, scope, ask
//   • Provide a small Settings modal to configure OpenAI API key/model/base URL
//   • Ensure we only boot once even if called twice (shim + direct import)

import { initHistory } from "./history.js";
import { initScopeControls } from "./scope.js";
import { initAskForm } from "./ask.js";

// Tiny helpers (cookie + CSRF) so we can POST to /debug/openai/
function cookie(name) {
  const m = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[2]) : "";
}

function csrfToken() {
  const el = document.querySelector('input[name="csrfmiddlewaretoken"]');
  if (el && el.value) return el.value;
  return cookie("csrftoken") || "";
}

let booted = false;

function initSettingsUI(root) {
  const toolbarRight = root.querySelector(".qaw-toolbar .qaw-right");
  if (!toolbarRight || toolbarRight.__pcSettingsWired) return;
  toolbarRight.__pcSettingsWired = true;

  // --- Button in the toolbar ---
  const btn = document.createElement("button");
  btn.type = "button";
  btn.id = "pc-q-settings-btn";
  btn.className = "btn";
  btn.textContent = "Settings";
  btn.title = "Configure OpenAI key and diagnostics";

  toolbarRight.appendChild(btn);

  // --- Modal markup ---
  const modal = document.createElement("div");
  modal.id = "pc-q-settings-modal";
  modal.style.position = "fixed";
  modal.style.inset = "0";
  modal.style.background = "rgba(15,23,42,0.55)";
  modal.style.display = "none";
  modal.style.alignItems = "center";
  modal.style.justifyContent = "center";
  modal.style.zIndex = "9999";
  modal.setAttribute("aria-hidden", "true");

  modal.innerHTML = `
    <div style="
      background: #0b1120;
      color: #e5e7eb;
      padding: 16px 18px;
      border-radius: 10px;
      box-shadow: 0 18px 45px rgba(0,0,0,.6);
      max-width: 420px;
      width: 100%;
      font: 13px/1.4 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    ">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div>
          <div style="font-weight:600;font-size:14px;">Workspace settings</div>
          <div style="opacity:.7;font-size:12px;">
            Stored in this browser and applied to this server process only.
          </div>
        </div>
        <button type="button" id="pc-q-settings-close" class="btn" style="padding:2px 8px;">✕</button>
      </div>

      <div style="display:flex;flex-direction:column;gap:8px;margin-top:4px;">
        <label style="display:flex;flex-direction:column;gap:2px;">
          <span>OpenAI API key</span>
          <input id="pc-openai-key" type="password" autocomplete="off"
                 placeholder="sk-..."
                 style="padding:6px 8px;border-radius:6px;border:1px solid #1f2937;background:#020617;color:#e5e7eb;">
        </label>

        <label style="display:flex;flex-direction:column;gap:2px;">
          <span>Model <span style="opacity:.7">(optional)</span></span>
          <input id="pc-openai-model" type="text" autocomplete="off"
                 placeholder="gpt-4o-mini"
                 style="padding:6px 8px;border-radius:6px;border:1px solid #1f2937;background:#020617;color:#e5e7eb;">
        </label>

        <label style="display:flex;flex-direction:column;gap:2px;">
          <span>Base URL <span style="opacity:.7">(optional, for self-hosted/proxy)</span></span>
          <input id="pc-openai-base-url" type="text" autocomplete="off"
                 placeholder="https://api.openai.com/v1"
                 style="padding:6px 8px;border-radius:6px;border:1px solid #1f2937;background:#020617;color:#e5e7eb;">
        </label>

        <label style="display:flex;align-items:center;gap:6px;margin-top:6px;font-size:12px;opacity:.9;">
          <input id="pc-diag-enable" type="checkbox">
          <span>Enable Library diagnostics overlay</span>
        </label>
      </div>

      <div id="pc-q-settings-status"
           style="margin-top:10px;font-size:12px;min-height:16px;opacity:.8;"></div>

      <div style="margin-top:10px;display:flex;justify-content:flex-end;gap:8px;">
        <button type="button" id="pc-q-settings-cancel" class="btn">Cancel</button>
        <button type="button" id="pc-q-settings-save" class="btn btn--primary">Save</button>
      </div>

      <div style="margin-top:8px;font-size:11px;opacity:.6;">
        Only use this on your own machine. The key is sent to this Paperclip
        server and stored in process memory (not in the database).
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  const keyInput = modal.querySelector("#pc-openai-key");
  const modelInput = modal.querySelector("#pc-openai-model");
  const baseInput = modal.querySelector("#pc-openai-base-url");
  const diagCheckbox = modal.querySelector("#pc-diag-enable");
  const statusEl = modal.querySelector("#pc-q-settings-status");
  const closeBtn = modal.querySelector("#pc-q-settings-close");
  const cancelBtn = modal.querySelector("#pc-q-settings-cancel");
  const saveBtn = modal.querySelector("#pc-q-settings-save");

  function loadFromLocal() {
    try {
      keyInput.value = localStorage.getItem("pcOpenaiKey") || "";
      modelInput.value = localStorage.getItem("pcOpenaiModel") || "";
      baseInput.value = localStorage.getItem("pcOpenaiBaseUrl") || "";
      const hasParam = new URL(location.href).searchParams.has("diag");
      const stored = localStorage.getItem("pcDiag") === "1";
      diagCheckbox.checked = hasParam || stored;
    } catch {
      // ignore
    }
  }

  function openModal() {
    loadFromLocal();
    statusEl.textContent = "";
    modal.style.display = "flex";
    modal.setAttribute("aria-hidden", "false");
    keyInput.focus();
  }

  function closeModal() {
    modal.style.display = "none";
    modal.setAttribute("aria-hidden", "true");
  }

  btn.addEventListener("click", () => openModal());

  closeBtn?.addEventListener("click", () => closeModal());
  cancelBtn?.addEventListener("click", () => closeModal());

  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  window.addEventListener("keydown", (e) => {
    if (modal.style.display === "flex" && e.key === "Escape") {
      e.preventDefault();
      closeModal();
    }
  });

  async function saveSettings() {
    const apiKey = keyInput.value.trim();
    const model = modelInput.value.trim();
    const baseUrl = baseInput.value.trim();

    if (!apiKey) {
      statusEl.textContent = "Please enter an API key.";
      statusEl.style.color = "#fca5a5";
      return;
    }

    // Persist in this browser
    try {
      localStorage.setItem("pcOpenaiKey", apiKey);
      localStorage.setItem("pcOpenaiModel", model);
      localStorage.setItem("pcOpenaiBaseUrl", baseUrl);
    } catch {
      // ignore
    }

    // Toggle diagnostics preference (shared with diagnostics.js: pcDiag + ?diag)
    const url = new URL(location.href);
    if (diagCheckbox.checked) {
      url.searchParams.set("diag", "1");
      try {
        localStorage.setItem("pcDiag", "1");
        localStorage.setItem("pc-diag", "1");
      } catch {
        // ignore
      }
    } else {
      url.searchParams.delete("diag");
      try {
        localStorage.removeItem("pcDiag");
        localStorage.removeItem("pc-diag");
      } catch {
        // ignore
      }
    }

    statusEl.textContent = "Saving…";
    statusEl.style.color = "#e5e7eb";

    // Send to backend so QAEngine picks it up via os.getenv("OPENAI_API_KEY").
    try {
      const resp = await fetch("/debug/openai/", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": csrfToken(),
          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        body: new URLSearchParams({
          api_key: apiKey,
          model,
          base_url: baseUrl,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data.ok) {
        throw new Error(data.error || `HTTP ${resp.status}`);
      }
      statusEl.textContent = "Saved. Changes apply to this server process.";
      statusEl.style.color = "#bbf7d0";
      // Reload to apply diagnostics overlay toggle immediately
      setTimeout(() => {
        location.href = url.toString();
      }, 400);
    } catch (err) {
      statusEl.textContent = `Save failed: ${String(err.message || err)}`;
      statusEl.style.color = "#fecaca";
    }
  }

  saveBtn?.addEventListener("click", () => {
    void saveSettings();
  });
}

export function initQaw(root) {
  if (booted) return;
  booted = true;

  const shell = root || document.getElementById("pc-qaw");
  if (!shell) return;

  const colId = shell.dataset.colId || "";
  const postUrl = shell.dataset.postUrl || "";
  if (!postUrl) return;

  // Scope controls (mode, year range, limit, trace toggle)
  const scope = initScopeControls({ root: shell });

  // History sidebar (localStorage + list UI)
  let askApi = null;

  const history = initHistory({
    root: shell,
    colId,
    onSelect(question) {
      if (askApi && typeof askApi.runWithQuestion === "function") {
        askApi.runWithQuestion(question);
      }
    },
  });

  // Ask bar + answer renderer
  askApi = initAskForm({
    root: shell,
    postUrl,
    history,
    scope,
  });

  // Settings menu (OpenAI key + diagnostics)
  initSettingsUI(shell);
}

// Auto-boot when loaded as a plain module script
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => initQaw());
} else {
  initQaw();
}
