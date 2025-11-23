// services/server/paperclip/static/captures/qaw/ask.js
// Ask bar + splash + answer rendering (exec summary, sources, trace).

function cookie(name) {
  const m = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[2]) : "";
}

function csrfToken(root) {
  return (
    cookie("csrftoken") ||
    root.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
    ""
  );
}

function escapeHtml(s) {
  return String(s ?? "").replace(
    /[&<>\"']/g,
    (m) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[m]
  );
}

function mdList(items) {
  if (!items || !items.length) {
    return "<ul class='muted'><li>—</li></ul>";
  }
  return (
    "<ul>" + items.map((x) => `<li>${escapeHtml(String(x))}</li>`).join("") + "</ul>"
  );
}

function renderBars(hist) {
  if (!hist || !hist.length) return "<div class='muted'>—</div>";
  const mx = Math.max(...hist.map((h) => Number(h.count) || 1), 1);
  return `<div class="bars">${hist
    .map(
      (h) => `
      <div class="bar">
        <div class="bar__label">${escapeHtml(String(h.label))}</div>
        <div class="bar__track">
          <span style="width:${Math.round((Number(h.count || 0) / mx) * 100)}%"></span>
        </div>
        <div class="bar__count">${Number(h.count || 0)}</div>
      </div>`
    )
    .join("")}</div>`;
}

function renderTrace(nodes, traceVisible) {
  if (!nodes || !nodes.length) return "";
  const one = (n) => `
      <details open class="trace-node">
        <summary>
          ${escapeHtml(n.title || "")}${
            n.note ? ` <span class="muted">— ${escapeHtml(n.note)}</span>` : ""
          }
        </summary>
        ${
          n.children && n.children.length
            ? `<div class="trace-children">${n.children.map(one).join("")}</div>`
            : ""
        }
      </details>`;
  return `<div class="qaw-trace" style="display:${
    traceVisible ? "block" : "none"
  }">${nodes.map(one).join("")}</div>`;
}

function renderSources(srcs) {
  if (!srcs || !srcs.length) {
    return "<div class='muted'>No sources found in scope.</div>";
  }
  return `<div class="sources">${srcs
    .map(
      (s) => `
      <div class="src">
        <div class="src__title">
          <a class="link" href="/captures/${s.id}/" target="_blank" rel="noopener">
            ${escapeHtml(s.title || "")}
          </a>
        </div>
        <div class="src__meta muted">
          ${escapeHtml(s.journal || "")}${
            s.year ? " · " + escapeHtml(String(s.year)) : ""
          }
        </div>
      </div>`
    )
    .join("")}</div>`;
}

export function initAskForm({ root, postUrl, history, scope }) {
  const askInput = root.querySelector("#pc-q-input");
  const runBtn = root.querySelector("#pc-q-run");
  const answerWrap = root.querySelector("#pc-answer");
  const splash = root.querySelector("#pc-splash");
  const splashInput = root.querySelector("#pc-q-input-splash");
  const splashBtn = root.querySelector("#pc-q-run-splash");

  if (!askInput || !runBtn || !answerWrap) {
    return { runWithQuestion() {} };
  }

  let hasAnswer = false;

  function maybeShowSplash() {
    if (!splash) return;
    const none = (history && history.isEmpty && history.isEmpty()) || false;
    splash.hidden = !(none && !hasAnswer);
  }

  function setLoading(on) {
    runBtn.disabled = !!on;
    runBtn.textContent = on ? "Running…" : "Run";
    if (on) {
      answerWrap.innerHTML = '<div class="qaw-loading">Thinking…</div>';
    }
  }

  async function ask() {
    const q = (askInput.value || "").trim();
    if (!q) return;

    setLoading(true);
    try {
      const body = {
        q,
        method: scope?.getMode ? scope.getMode() : "hybrid",
        year_min: scope?.getYearMin ? scope.getYearMin() : null,
        year_max: scope?.getYearMax ? scope.getYearMax() : null,
        limit: scope?.getLimit ? scope.getLimit() : 30,
      };

      const resp = await fetch(postUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(root),
        },
        body: JSON.stringify(body),
        credentials: "same-origin",
      });

      const j = await resp.json();
      if (!j.ok) throw new Error(j.error || "error");

      if (history && history.add) history.add(q);
      hasAnswer = true;
      maybeShowSplash();

      const A = j.answer || {};
      const direct = A.direct;

      answerWrap.innerHTML = `
        <div class="answer-head">
          <div class="muted">Draft</div>
          <div class="answer-actions">
            <button class="btn" id="pc-rerun">Rerun</button>
          </div>
        </div>

        ${
          A.intent === "methods" && direct
            ? `
          <h2>Direct answer</h2>
          <p class="muted">Question: <em>${escapeHtml(A.question || "")}</em></p>
          <h3>${escapeHtml(direct.title || "Answer")}</h3>
          ${mdList(direct.bullets || [])}
          ${
            direct.designs && direct.designs.length
              ? `<h4>Study designs</h4>${mdList(direct.designs)}`
              : ""
          }
        `
            : ""
        }

        <h2>Executive summary</h2>
        ${mdList(A.summary?.executive || [])}

        <h3>Agreements</h3>
        ${mdList(A.summary?.agreements)}

        <h3>Disagreements</h3>
        ${mdList(A.summary?.disagreements)}

        <h3>Gaps & What’s missing</h3>
        ${mdList(A.summary?.gaps)}

        <div class="split">
          <div class="half">
            <h3>Coverage<br><span class="muted">By year</span></h3>
            ${renderBars(A.summary?.coverage_by_year)}
          </div>
        </div>

        <h3>Sources</h3>
        ${renderSources(A.sources)}

        ${renderTrace(
          A.trace,
          scope?.getTraceVisible ? scope.getTraceVisible() : false
        )}
      `;

      root.querySelector("#pc-rerun")?.addEventListener("click", ask);
    } catch (e) {
      const msg = (e && e.message) || String(e) || "Unknown error";
      answerWrap.innerHTML = `<div class="qaw-error">Failed to run: ${escapeHtml(
        msg
      )}</div>`;
    } finally {
      setLoading(false);
      scope?.updateChips?.();
    }
  }

  // Ask bar events
  runBtn.addEventListener("click", ask);
  askInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      runBtn.click();
    }
  });

  // Splash (hero) interactions
  if (splash) {
    splash.addEventListener("click", (e) => {
      const idea = e.target.closest(".qaw-idea");
      if (!idea) return;
      const q = idea.textContent.trim();
      if (!q) return;
      askInput.value = q;
      ask();
    });
  }
  splashBtn?.addEventListener("click", () => {
    const q = (splashInput?.value || "").trim();
    if (!q) return;
    askInput.value = q;
    ask();
  });
  splashInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      splashBtn?.click();
    }
  });

  // Initial hero state
  maybeShowSplash();

  return {
    runWithQuestion(question) {
      askInput.value = question || "";
      ask();
    },
  };
}
