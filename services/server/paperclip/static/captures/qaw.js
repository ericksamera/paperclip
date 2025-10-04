// services/server/paperclip/static/captures/qaw.js
(function () {
  const root = document.getElementById("pc-qaw");
  if (!root) return;

  const colId = root.dataset.colId;
  const POST_URL = root.dataset.postUrl;

  function cookie(name){ const m=document.cookie.match(new RegExp("(^|; )"+name+"=([^;]*)")); return m?decodeURIComponent(m[2]):""; }
  function csrfToken(){ return cookie("csrftoken") || document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || ""; }

  const askInput   = document.getElementById("pc-q-input");
  const runBtn     = document.getElementById("pc-q-run");
  const answerWrap = document.getElementById("pc-answer");
  const splash     = document.getElementById("pc-splash");
  const splashInput= document.getElementById("pc-q-input-splash");
  const splashBtn  = document.getElementById("pc-q-run-splash");
  const qList      = document.getElementById("pc-q-list");
  const qFilter    = document.getElementById("pc-q-filter");
  const yearMin    = document.getElementById("pc-year-min");
  const yearMax    = document.getElementById("pc-year-max");
  const limitEl    = document.getElementById("pc-limit");
  const modeBtns   = document.querySelectorAll(".seg__btn");
  const traceToggle= document.getElementById("pc-trace-toggle");
  const chips = {
    mode:  document.getElementById("pc-mode-chip"),
    limit: document.getElementById("pc-limit-chip"),
    scope: document.getElementById("pc-scope-chip"),
  };

  let mode = "hybrid";
  let showTrace = false;
  let hasAnswer = false;

  const KEY = `pc:qaw:${colId}:qs`;
  function loadQs(){ try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch(_) { return []; } }
  function saveQs(list){ try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, 200))); } catch(_) {} }
  function addQ(item){ const list = loadQs(); list.unshift({ id: Date.now(), q: item.q, at: new Date().toISOString() }); saveQs(list); renderQList(list); maybeShowSplash(); }

  function renderQList(list){
    const filt = (qFilter.value || "").toLowerCase();
    qList.innerHTML = list
      .filter(x => !filt || x.q.toLowerCase().includes(filt))
      .map(x => `
        <button class="qaw-q" title="${escapeHtml(x.q)}" data-q="${encodeURIComponent(x.q)}">
          <div class="qaw-q__title">${escapeHtml(x.q)}</div>
          <div class="qaw-q__meta muted">${new Date(x.at).toLocaleString()}</div>
        </button>
      `).join("");
  }

  function maybeShowSplash(){
    const none = (loadQs().length === 0) && !hasAnswer;
    if (splash) splash.hidden = !none;
  }

  function bindSplash(){
    if (!splash) return;
    splash.addEventListener("click", (e) => {
      const idea = e.target.closest(".qaw-idea");
      if (!idea) return;
      const q = idea.textContent.trim();
      askInput.value = q;
      ask();
    });
    if (splashBtn) splashBtn.addEventListener("click", () => {
      const q = (splashInput.value || "").trim();
      if (!q) return;
      askInput.value = q;
      ask();
    });
    splashInput?.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); splashBtn?.click(); } });
  }

  qFilter.addEventListener("input", () => renderQList(loadQs()));
  qList.addEventListener("click", (e) => {
    const btn = e.target.closest(".qaw-q"); if (!btn) return;
    const q = decodeURIComponent(btn.dataset.q || ""); askInput.value = q; runBtn.click();
  });

  modeBtns.forEach(b => b.addEventListener("click", () => {
    modeBtns.forEach(x => x.classList.remove("seg__btn--active"));
    b.classList.add("seg__btn--active"); mode = b.dataset.mode || "hybrid"; chips.mode.textContent = mode;
  }));

  function updateChips(){
    chips.limit.textContent = String(limitEl.value || 30);
    const a = (yearMin.value || "").trim(), b = (yearMax.value || "").trim();
    chips.scope.textContent = (a || b) ? `${a || "—"}–${b || "—"}` : "all years";
  }
  yearMin.addEventListener("input", updateChips);
  yearMax.addEventListener("input", updateChips);
  limitEl.addEventListener("input", updateChips);

  traceToggle.addEventListener("click", () => {
    showTrace = !showTrace;
    traceToggle.textContent = showTrace ? "Hide reasoning trace" : "Show reasoning trace";
    document.querySelectorAll(".qaw-trace").forEach(el => el.style.display = showTrace ? "block" : "none");
  });

  function escapeHtml(s){ return String(s ?? "").replace(/[&<>"']/g, m => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[m])); }
  function mdList(items){ if (!items || !items.length) return "<ul class='muted'><li>—</li></ul>"; return "<ul>" + items.map(x => `<li>${escapeHtml(x)}</li>`).join("") + "</ul>"; }
  function renderBars(hist){
    if (!hist || !hist.length) return "<div class='muted'>—</div>";
    const mx = Math.max(...hist.map(h => Number(h.count) || 1));
    return `<div class="bars">${hist.map(h => `
      <div class="bar">
        <div class="bar__label">${escapeHtml(String(h.label))}</div>
        <div class="bar__track"><span style="width:${Math.round((h.count/mx)*100)}%"></span></div>
        <div class="bar__count">${h.count}</div>
      </div>`).join("")}</div>`;
  }
  function renderTrace(nodes){
    if (!nodes || !nodes.length) return "";
    const one = (n) => `
      <details open class="trace-node">
        <summary>${escapeHtml(n.title || "")}${n.note ? ` <span class="muted">— ${escapeHtml(n.note)}</span>` : ""}</summary>
        ${n.children ? `<div class="trace-children">${n.children.map(one).join("")}</div>` : ""}
      </details>`;
    return `<div class="qaw-trace" style="display:${showTrace ? 'block' : 'none'}">${nodes.map(one).join("")}</div>`;
  }
  function renderSources(srcs){
    if (!srcs || !srcs.length) return "<div class='muted'>No sources found in scope.</div>";
    return `<div class="sources">${srcs.map(s => `
      <div class="src">
        <div class="src__title"><a class="link" href="/captures/${s.id}/" target="_blank" rel="noopener">${escapeHtml(s.title)}</a></div>
        <div class="src__meta muted">${escapeHtml(s.journal || "")} ${s.year ? "· " + escapeHtml(String(s.year)) : ""}</div>
      </div>`).join("")}</div>`;
  }

  function setLoading(on){
    runBtn.disabled = !!on;
    runBtn.textContent = on ? "Running…" : "Run";
    if (on) answerWrap.innerHTML = `<div class="qaw-loading">Thinking…</div>`;
  }

  async function ask(){
    const q = (askInput.value || "").trim();
    if (!q) return;
    setLoading(true);
    try {
      const body = {
        q,
        method: mode,
        year_min: (yearMin.value || "").trim() || null,
        year_max: (yearMax.value || "").trim() || null,
        limit: Number(limitEl.value || 30)
      };
      const resp = await fetch(POST_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(body),
        credentials: "same-origin"
      });
      const j = await resp.json();
      if (!j.ok) throw new Error(j.error || "error");

      addQ({ q });
      hasAnswer = true; maybeShowSplash();

      const A = j.answer || {};
      const direct = A.direct;

      answerWrap.innerHTML = `
        <div class="answer-head">
          <div class="muted">Draft</div>
          <div class="answer-actions"><button class="btn" id="pc-rerun">Rerun</button></div>
        </div>

        ${A.intent === "methods" && direct ? `
          <h2>Direct answer</h2>
          <p class="muted">Question: <em>${escapeHtml(A.question || "")}</em></p>
          <h3>${escapeHtml(direct.title || "Answer")}</h3>
          ${mdList(direct.bullets || [])}
          ${direct.designs && direct.designs.length ? `<h4>Study designs</h4>${mdList(direct.designs)}` : ""}
        ` : ""}

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

        ${renderTrace(A.trace)}
      `;
      document.getElementById("pc-rerun")?.addEventListener("click", ask);
    } catch (e) {
      answerWrap.innerHTML = `<div class="qaw-error">Failed to run: ${String(e && e.message || e)}</div>`;
    } finally {
      setLoading(false);
      updateChips();
    }
  }

  runBtn.addEventListener("click", ask);
  askInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); runBtn.click(); } });

  // init
  function boot(){
    renderQList(loadQs());
    updateChips();
    bindSplash();
    maybeShowSplash();
  }
  boot();
})();
