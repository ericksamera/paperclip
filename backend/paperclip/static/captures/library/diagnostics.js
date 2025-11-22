// services/server/paperclip/static/captures/library/diagnostics.js
(function () {
  const WANT = new URL(location.href).searchParams.has("diag") ||
               localStorage.getItem("pcDiag") === "1";

  // Minimal UI
  const box = document.createElement("div");
  box.id = "pc-diag";
  Object.assign(box.style, {
    position: "fixed", top: "12px", right: "12px", zIndex: 999999,
    background: "rgba(20,20,25,.92)", color: "#fff",
    padding: "10px 12px", borderRadius: "8px", boxShadow: "0 10px 30px rgba(0,0,0,.35)",
    font: "500 12px/1.35 system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
    display: "none", minWidth: "260px"
  });
  box.innerHTML = `<div style="opacity:.8;margin-bottom:6px">Paperclip diagnostics</div>`;
  const list = document.createElement("div"); box.appendChild(list);
  function row(label, ok, hint = "") {
    const el = document.createElement("div");
    el.style.margin = "4px 0";
    el.innerHTML = `<span style="opacity:.8">${label}</span> — <b style="color:${ok?'#7dff9e':'#ff8c8c'}">${ok?'OK':'FAIL'}</b>` +
                   (hint ? `<div style="opacity:.75;margin-top:2px">${hint}</div>` : "");
    list.appendChild(el);
    if (!ok && box.style.display !== "block") {
      box.style.display = "block";
    }
  }

  // Surface module import errors (e.g. "does not provide an export named")
  window.addEventListener("error", (e) => {
    const msg = String(e?.message || "");
    if (/does not provide an export named|Unexpected token/.test(msg)) {
      row("Module import", false, msg);
      box.style.display = "block";
    }
  });

  document.addEventListener("DOMContentLoaded", async () => {
    if (WANT) box.style.display = "block";
    document.body.appendChild(box);

    // Did the main bundle run?
    row("index.js booted", !!window.__pcIndexBooted,
        !!window.__pcIndexBooted ? "" : "Main entry didn’t mark __pcIndexBooted.");

    // Was selection module loaded?
    const selLoaded = !!window.__pcSelectionESM || !!window.__pcSelectionESMReady;
    row("selection.js loaded", selLoaded,
        selLoaded ? "" : "Look for an earlier import error in console.");

    // Quick click test (non-destructive)
    const tb = document.getElementById("pc-body") || document.querySelector(".pc-table tbody");
    const tr = tb && (tb.querySelector("tr.pc-row") || tb.querySelector("tr"));
    if (!tr) {
      row("table/rows present", false, "Couldn’t find #pc-body rows.");
      return;
    }

    const before = tr.getAttribute("aria-selected") || "false";
    tr.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    setTimeout(async () => {
      const after = tr.getAttribute("aria-selected") || "false";
      const ok = before !== after && after === "true";
      row("row click toggles selection", ok,
          ok ? "" : "Selection wiring didn’t react to click.");

      // Clean up by clearing selection if API is present
      try { const mod = await import("./selection.js");
            if (mod?.clearSelection) mod.clearSelection(); } catch {}
    }, 60);
  });
})();
