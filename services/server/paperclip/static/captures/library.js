// services/server/paperclip/static/captures/library.js
// Library polish: sticky tooling + chips + infinite scroll + hotkeys
// PLUS: right-click context menu + drag & drop to Collections.
// NEW: collection context menu (rename/delete), modal create/rename,
//      sidebar collapsible groups, and "Remove from this collection" when filtered by a collection.
// NEW: 3-state search mode chips (Text / Semantic / Hybrid) + better empty states (handled by template).


(function () {

  if (window.__pcESMSelectionReady) {
    try { console.info("[paperclip] classic captures/library.js skipped (ESM active)"); } catch (_) {}
    return;
  }

  const shell  = document.getElementById('z-shell');
  const tbody  = document.getElementById('pc-body');
  const zLeft  = document.getElementById('z-left');
  const zCenter= document.querySelector('.z-center');
  if (!shell || !tbody) return;

  // -------------------- helpers --------------------
  const selected = new Set();
  const bulkForm = document.getElementById('pc-bulk-form');

  const assignSelect = document.getElementById('pc-assign-select');
  const assignAdd    = document.getElementById('pc-assign-add');
  const assignRemove = document.getElementById('pc-assign-remove');

  const colsBtn    = document.getElementById('pc-cols-toggle');
  const colsPanel  = document.getElementById('pc-cols-panel');
  const colsClose  = document.getElementById('pc-cols-close');
  const colsReset  = document.getElementById('pc-cols-reset');

  const searchInput = document.querySelector('.z-search input[name=q]');
  const searchModeInput = document.querySelector('.z-search input[name=search]');
  const modeChips = document.querySelectorAll('.z-mode-chip');
  const colAddBtn   = document.getElementById('pc-col-add-btn');

  // --- Helpers delegated to captures/library/dom.js ---
  function csrfToken()            { return window.PCDOM?.csrfToken?.() || ""; }
  function escapeHtml(s)          { return window.PCDOM?.escapeHtml?.(s) || String(s ?? ""); }
  function buildQs(next)          { return window.PCDOM?.buildQs?.(next) || location.search; }
  function keepOnScreen(el)       { return window.PCDOM?.keepOnScreen?.(el); }
  function currentCollectionId()  { return window.PCDOM?.currentCollectionId?.() || ""; }
  function scanCollections()      { return window.PCDOM?.scanCollections?.() || []; }

  // ---- Debounced search-as-you-type ----
  let searchTimer = null;
  let searchAbort = null;

  function setSearchLoading(on){
    document.querySelector('.z-search')?.classList.toggle('is-loading', !!on);
  }
  function pushUrlForQuery(q){
    const url = buildQs({ q: (q && q.trim()) || null, page: null });
    history.replaceState({}, '', url);
  }
  async function fetchAndReplaceTable(url, signal){
    const resp = await fetch(url, { headers: { 'X-Requested-With': 'fetch' }, signal });
    if (!resp.ok) return false;
    const html = await resp.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const newBody = doc.querySelector('#pc-body');
    if (!newBody) return false;
    // Clear selection, replace rows, reset details
    clearSelection();
    tbody.innerHTML = newBody.innerHTML;
    if (info) info.innerHTML = '<div class="z-info-empty">Select an item to see details.</div>';
    return true;
  }

  // NEW: Search mode chips wiring
  function urlParamsObj() {
    const u = new URL(location.href);
    const o = {};
    u.searchParams.forEach((v, k) => { if (v !== '') o[k] = v; });
    return o;
  }
  function setModeUI(targetMode){
    modeChips.forEach(btn => {
      const on = (btn.dataset.mode || '') === (targetMode || '');
      btn.classList.toggle('active', on);
    });
  }
  function setSearchMode(mode){
    const val = (mode || '').trim();
    if (searchModeInput) searchModeInput.value = val;
    setModeUI(val);
    setSearchLoading(true);
    const url = buildQs({ search: (val || null), q: (searchInput?.value || '').trim() || null, page: null });
    // fetch rendered HTML and swap table
    fetchAndReplaceTable(url).catch(()=>{}).finally(() => {
      setSearchLoading(false);
      // keep focus in the input
      if (searchInput){
        searchInput.focus();
        const L = searchInput.value.length;
        searchInput.setSelectionRange(L, L);
      }
      history.replaceState({}, '', url);
    });
  }
  // Initialize chips active state from URL (in case server cache missed)
  (function initModeFromUrl(){
    const prm = urlParamsObj();
    const cur = (prm.search || (searchModeInput?.value || '')).trim();
    setModeUI(cur);
  })();
  // Click handlers
  modeChips.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const mode = btn.dataset.mode || '';
      setSearchMode(mode);
    });
  });

  searchInput?.addEventListener('input', () => {
    const q = searchInput.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      setSearchLoading(true);
      try {
        if (searchAbort) searchAbort.abort();
        const ctl = new AbortController(); searchAbort = ctl;
        const url = buildQs({ q: q || null, page: null });
        const ok = await fetchAndReplaceTable(url, ctl.signal);
        if (ok) pushUrlForQuery(q);
      } catch(_) { /* ignore */ }
      finally {
        setSearchLoading(false);
        // keep focus in the box
        searchInput.focus(); searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);
      }
    }, 250); // 200–300ms sweet spot
  });


  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(^|; )' + name + '=([^;]*)'));
    return m ? decodeURIComponent(m[2]) : '';
  }

  // -------------------- selection --------------------
  function updateBulk() {
    if (!bulkBtn) return;
    bulkBtn.disabled = selected.size === 0;
    bulkBtn.textContent = selected.size ? `Delete (${selected.size})` : 'Delete selected';
  }
  function toggleRow(tr, on) {
    if (!tr || !tr.dataset.id) return;
    const next = (on === undefined) ? (tr.getAttribute('aria-selected') !== 'true') : !!on;
    tr.setAttribute('aria-selected', next ? 'true' : 'false');
    if (next) selected.add(tr.dataset.id); else selected.delete(tr.dataset.id);
    updateBulk();
    if (next) renderDetailsFromRow(tr);
  }
  function clearSelection(){
    tbody.querySelectorAll('tr.pc-row[aria-selected="true"]').forEach(tr => toggleRow(tr, false));
  }
  function lastSelectedRow(){
    const ids = Array.from(selected);
    if (!ids.length) return null;
    const lastId = ids[ids.length - 1];
    return tbody.querySelector(`tr.pc-row[data-id="${CSS.escape(lastId)}"]`);
  }

  tbody.addEventListener('click', (e) => {
    const tr = e.target.closest('tr.pc-row');
    if (!tr) return;
    if (e.target.closest('a')) return; // allow link clicks
    toggleRow(tr);
  });
  let lastIndex = null;
  function rowIndex(tr) { return [...tbody.querySelectorAll('tr.pc-row')].indexOf(tr); }
  tbody.addEventListener('mousedown', (e) => {
    const tr = e.target.closest('tr.pc-row'); if (!tr) return;
    if (e.shiftKey && lastIndex !== null) {
      e.preventDefault();
      const rows = [...tbody.querySelectorAll('tr.pc-row')];
      const i = rowIndex(tr); const [a,b] = i < lastIndex ? [i,lastIndex] : [lastIndex,i];
      rows.slice(a,b+1).forEach(r => toggleRow(r, true));
    } else {
      lastIndex = rowIndex(tr);
    }
  });

  // ---- Bulk delete is owned by captures/library/bulk_delete.js ----
  // Keep keyboard shortcut behavior: trigger the real module's handler.
  const bulkBtn = document.getElementById('pc-bulk-delete');
  function _triggerBulkDelete() { bulkBtn?.click(); }

  // If your original keydown handler referenced performBulkDelete(), keep it,
  // but make it call the stub:
  window.addEventListener('keydown', (e) => {
    const tag = (e.target && (e.target.tagName || '')).toLowerCase();
    const typing = tag === 'input' || tag === 'textarea' || e.target.isContentEditable;
    if (!typing && (e.key === 'Delete' || e.key === 'Backspace')) {
      e.preventDefault();
      _triggerBulkDelete();
    }
  }, { capture: true });

  // Ensure we don’t lose a pending delete on navigation
  window.addEventListener('beforeunload', () => {
    if (pendingDelete && !pendingDelete.sent) {
      try { pendingDelete.flushNow && pendingDelete.flushNow(); } catch (_) {}
    }
  });

  // Keep the button working if it exists, but hide UI (you don’t want it)
  if (bulkBtn) {
    try { bulkBtn.style.display = 'none'; } catch (_) {}
    try { bulkForm && (bulkForm.style.display = 'none'); } catch (_) {}
    bulkBtn.addEventListener('click', (e) => { e.preventDefault(); performBulkDelete(); });
  } else {
    // Fallback: if the button isn’t in the DOM, still support Delete/Backspace
    const isTypingTarget = (t) => {
      const tag = (t && (t.tagName || '')).toLowerCase();
      return tag === 'input' || tag === 'textarea' || (t && t.isContentEditable);
    };
    window.addEventListener('keydown', (e) => {
      if (!isTypingTarget(e.target) && (e.key === 'Delete' || e.key === 'Backspace') && selected.size) {
        e.preventDefault();
        performBulkDelete();
      }
    });
  }
  // -------------------- info panel + splitters --------------------
  const info = document.getElementById('z-info');
  const toggleRightBtn = document.getElementById('z-toggle-right');
  const toggleLeftBtn  = document.getElementById('z-toggle-left');

  function truncate(s, n) { return (s && s.length > n) ? (s.slice(0, n - 1) + '…') : s; }
  function safeHostname(u) { try { return new URL(u, location.href).hostname; } catch { return ''; } }

  function renderDetailsFromRow(tr) {
    if (!info) return;
    const title = tr.dataset.title || '(Untitled)';
    const url = tr.dataset.url || '';
    const site = safeHostname(url);
    const authors = tr.dataset.authors || '';
    const journal = tr.dataset.journal || '';
    const year = tr.dataset.year || '';
    const doi = tr.dataset.doi || '';
    const doiUrl = tr.dataset.doiUrl || '';
    const abs = tr.dataset.abstract || '';
    const kws = (tr.dataset.keywords || '').split(',').map(s => s.trim()).filter(Boolean);

    info.innerHTML = `
      <h3>${escapeHtml(title)}</h3>
      <div class="z-meta">${journal ? escapeHtml(journal) + ' · ' : ''}${year ? year + ' · ' : ''}${site ? escapeHtml(site) : ''}</div>
      ${authors ? `<div class="z-meta">${escapeHtml(authors)}</div>` : ''}
      ${doi ? `<div class="z-meta"><a href="${doiUrl || ('https://doi.org/' + doi)}" target="_blank" rel="noopener">${escapeHtml(doi)}</a></div>` : ''}
      ${abs ? `<div class="z-meta"><strong>Abstract.</strong> ${escapeHtml(truncate(abs, 700))}</div>` : ''}
      ${kws.length ? `<div class="z-kws">${kws.map(k => `<span class="z-kw">${escapeHtml(k)}</span>`).join('')}</div>` : ''}
    `;
    openRight();
  }

  // left/right panel sizing + toggles
  function openRight() { shell.style.setProperty('--right-w', localStorage.getItem('pc-right-w') || '360px'); }
  function closeRight() { localStorage.setItem('pc-right-w', getComputedStyle(shell).getPropertyValue('--right-w').trim() || '360px'); shell.style.setProperty('--right-w', '0px'); }

  // NEW: proper left toggle with persistence
  function openLeft(){ shell.style.setProperty('--left-w', localStorage.getItem('pc-left-w') || '260px'); localStorage.setItem('pc-left-hidden', '0'); }
  function closeLeft(){ localStorage.setItem('pc-left-w', getComputedStyle(shell).getPropertyValue('--left-w').trim() || '260px'); shell.style.setProperty('--left-w', '0px'); localStorage.setItem('pc-left-hidden', '1'); }

  toggleRightBtn?.addEventListener('click', () => {
    const w = getComputedStyle(shell).getPropertyValue('--right-w').trim();
    if (w === '0px' || w === '0') openRight(); else closeRight();
  });

  toggleLeftBtn?.addEventListener('click', () => {
    const w = getComputedStyle(shell).getPropertyValue('--left-w').trim();
    if (w === '0px' || w === '0') openLeft(); else closeLeft();
  });

  // splitters
  makeSplitter('z-splitter-left', '--left-w', 160, 480, 'pc-left-w');
  makeSplitter('z-splitter-right', '--right-w', 0,   560, 'pc-right-w');

  function makeSplitter(id, varName, minPx, maxPx, storeKey) {
    const el = document.getElementById(id);
    if (!el) return;
    let dragging = false, startX = 0, startW = 0;
    el.addEventListener('mousedown', (e) => {
      dragging = true;
      startX = e.clientX;
      startW = parseInt(getComputedStyle(shell).getPropertyValue(varName), 10) || 0;
      document.body.style.userSelect = 'none';
    });
    window.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      let delta = e.clientX - startX;
      let next = varName === '--right-w' ? (startW - delta) : (startW + delta);
      next = Math.max(minPx, Math.min(maxPx, next));
      shell.style.setProperty(varName, next + 'px');
    });
    window.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      document.body.style.userSelect = '';
      const cur = getComputedStyle(shell).getPropertyValue(varName).trim();
      localStorage.setItem(storeKey, cur);
    });
    const saved = localStorage.getItem(storeKey);
    if (saved) shell.style.setProperty(varName, saved);
  }

  // apply persisted left-hidden on load (so the button actually hides the sidebar)
  (function initSidebars(){
    if (localStorage.getItem('pc-left-hidden') === '1') {
      shell.style.setProperty('--left-w', '0px');
    }
  })();


  // -------------------- Column preferences --------------------
  const COLS = [
    {key:'title'}, {key:'authors'}, {key:'year'}, {key:'journal'},
    {key:'doi'}, {key:'added'}, {key:'refs'}
  ];
  const DEFAULT_COLS = {
    show: {title:true, authors:true, year:true, journal:true, doi:false, added:true, refs:true},
    widths: {authors:'16', year:'6', journal:'24', doi:'24', added:'10', refs:'6'}
  };
  function readCols(){
    try { return JSON.parse(localStorage.getItem('pcCols') || '') || DEFAULT_COLS; }
    catch(_) { return DEFAULT_COLS; }
  }
  function saveCols(cfg){ try { localStorage.setItem('pcCols', JSON.stringify(cfg)); } catch(_) {} }
  function applyCols(cfg){
    COLS.forEach(({key}) => {
      const on = (key==='title') ? true : !!cfg.show[key];
      document.querySelectorAll(`[data-col="${key}"]`).forEach(el => { el.style.display = on ? '' : 'none'; });
    });
    Object.entries(cfg.widths || {}).forEach(([key, val]) => {
      const ch = String(val || '').trim();
      document.querySelectorAll(`[data-col="${key}"]`).forEach(el => el.style.width = ch ? (ch + 'ch') : '');
    });
  }
  function initColsUI(){
    const cfg = readCols();
    document.querySelectorAll('[data-col-toggle]').forEach(cb => {
      const k = cb.getAttribute('data-col-toggle');
      cb.checked = (k === 'title') ? true : !!cfg.show[k];
      cb.addEventListener('change', () => {
        if (k === 'title') return;
        cfg.show[k] = cb.checked; saveCols(cfg); applyCols(cfg);
      });
    });
    document.querySelectorAll('[data-col-width]').forEach(inp => {
      const k = inp.getAttribute('data-col-width');
      inp.value = (cfg.widths[k] || '');
      inp.addEventListener('input', () => {
        const v = inp.value.replace(/[^\d.]/g, '');
        cfg.widths[k] = v; saveCols(cfg); applyCols(cfg);
      });
    });
    colsReset?.addEventListener('click', () => {
      saveCols(DEFAULT_COLS); applyCols(DEFAULT_COLS); initColsUI();
    });
    applyCols(cfg);
  }
  colsBtn?.addEventListener('click', () => {
    const vis = colsPanel.style.display !== 'block';
    colsPanel.style.display = vis ? 'block' : 'none';
    if (vis) initColsUI();
  });
  colsClose?.addEventListener('click', () => { colsPanel.style.display = 'none'; });

  // -------------------- Filter chips --------------------
  (function initChips(){
    const toolbar = document.querySelector('.z-toolbar');
    if (!toolbar) return;
    const host = document.createElement('div');
    host.id = 'pc-chips';
    host.style.marginLeft = '8px';
    host.style.display = 'flex';
    host.style.flexWrap = 'wrap';
    host.style.gap = '6px';
    const afterTarget = document.querySelector('.z-search') || toolbar.firstElementChild;
    afterTarget?.insertAdjacentElement('afterend', host);
    function chip(label, onClose){
      const a = document.createElement('a');
      a.className = 'chip';
      a.href = '#';
      a.innerHTML = `${escapeHtml(label)}&nbsp;✕`;
      a.addEventListener('click', (e) => { e.preventDefault(); onClose(); });
      return a;
    }
    const params = (function(){
      const u = new URL(location.href);
      const o = {};
      u.searchParams.forEach((v,k)=>{ if (v !== '') o[k] = v; });
      return o;
    })();
    const colLabelFromDOM = (() => {
      const activeColLink = document.querySelector('.z-left .z-group:first-child .z-link.active .z-label');
      return activeColLink ? activeColLink.textContent.trim() : null;
    })();
    if (params.year) host.appendChild(chip(`Year: ${params.year}`, () => location.search = buildQs({year:null})));
    if (params.journal) host.appendChild(chip(`Journal`, () => location.search = buildQs({journal:null})));
    if (params.site) host.appendChild(chip(`Site: ${params.site}`, () => location.search = buildQs({site:null})));
    if (params.col) host.appendChild(chip(`Collection: ${colLabelFromDOM || params.col}`, () => location.search = buildQs({col:null})));
    if (!host.childElementCount) host.remove();
  })();

  // -------------------- Infinite scroll --------------------
  const statusEl = (() => {
    const el = document.createElement('div');
    el.id = 'pc-scroll-status';
    el.className = 'pc-scroll-status';
    el.textContent = '';
    shell.appendChild(el);
    return el;
  })();

  let total = null;
  let nextPage = null;
  let loading = false;

  async function fetchPage(pageNo){
    const base = new URL(location.origin + '/library/page/');
    const cur = new URL(location.href);
    cur.searchParams.forEach((v, k) => base.searchParams.set(k, v));
    if (!base.searchParams.get('per')) base.searchParams.set('per', '200');
    base.searchParams.set('page', String(pageNo));
    const r = await fetch(base.toString(), { credentials: 'same-origin' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  function rowHtml(r){
    const title = escapeHtml(r.title || r.url || '(Untitled)');
    const url   = r.url ? `<div class="pc-link"><a href="${escapeHtml(r.url)}" target="_blank" rel="noreferrer">${escapeHtml(r.site_label || '')}</a></div>` : '';
    const doi   = r.doi_url ? `<a href="${escapeHtml(r.doi_url)}" target="_blank" rel="noreferrer">${escapeHtml(r.doi)}</a>` : '';
    const authorsTitle = escapeHtml(r.authors_intext || '');
    const journalCell = `<td class="pc-col-tight" data-col="journal" title="${escapeHtml(r.journal || '')}">${escapeHtml(r.journal_short || r.journal || '')}</td>`;
    return `
<tr class="pc-row" draggable="true" data-id="${r.id}" aria-selected="false"
    data-title="${escapeHtml(r.title)}"
    data-authors="${authorsTitle}"
    data-year="${escapeHtml(r.year || '')}"
    data-journal="${escapeHtml(r.journal || '')}"
    data-doi="${escapeHtml(r.doi || '')}"
    data-doi-url="${escapeHtml(r.doi_url || '')}"
    data-url="${escapeHtml(r.url || '')}"
    data-abstract="${escapeHtml(r.abstract || '')}"
    data-keywords="${escapeHtml((r.keywords || []).join(', '))}">
  <td class="pc-col-title" data-col="title">
    <a class="pc-title" href="/captures/${r.id}/">${title}</a>
    ${url}
  </td>
  <td class="pc-col-tight" data-col="authors"><span class="pc-authors-inline" title="${authorsTitle}">${authorsTitle}</span></td>
  <td class="pc-col-tight" data-col="year">${escapeHtml(r.year || '')}</td>
  ${journalCell}
  <td class="pc-col-tight" data-col="doi">${doi}</td>
  <td class="pc-col-tight" data-col="added">${escapeHtml(r.added || '')}</td>
  <td class="pc-col-tight" data-col="refs">${escapeHtml(String(r.refs ?? ''))}</td>
</tr>`;
  }

  async function prefetchMeta(){
    try{
      const j = await fetchPage(1);
      total = j.page?.total ?? null;
      nextPage = j.page?.next_page ?? null;
      updateStatus();
    }catch(_){}
  }
  function loadedCount(){ return tbody.querySelectorAll('tr.pc-row').length; }
  function updateStatus(){
    if (total == null) { statusEl.textContent = ''; return; }
    statusEl.textContent = `Loaded ${loadedCount()} of ${total}`;
  }
  async function maybeLoadMore(){
    if (loading || nextPage == null) return;
    if (!zCenter) return;
    const nearBottom = (zCenter.scrollHeight - zCenter.scrollTop - zCenter.clientHeight) < 600;
    if (!nearBottom) return;
    loading = true;
    try{
      const j = await fetchPage(nextPage);
      const rows = j.rows || [];
      if (rows.length){
        const html = rows.map(rowHtml).join('');
        tbody.insertAdjacentHTML('beforeend', html);
        applyCols(readCols());
        ensureRowsDraggable();
      }
      nextPage = j.page?.next_page ?? null;
      updateStatus();
    }catch(e){ console.warn(e); }
    finally{ loading = false; }
  }
  if (zCenter){
    zCenter.addEventListener('scroll', maybeLoadMore, { passive: true });
    prefetchMeta();
  }

  // -------------------- Hotkeys --------------------
  function moveSelection(delta){
    const rows = [...tbody.querySelectorAll('tr.pc-row')];
    if (!rows.length) return;
    let idx = rows.findIndex(r => r.getAttribute('aria-selected') === 'true');
    if (idx === -1) idx = 0;
    else idx = Math.max(0, Math.min(rows.length - 1, idx + delta));
    clearSelection(); toggleRow(rows[idx], true);
    rows[idx].scrollIntoView({ block: 'nearest' });
  }
  function openCurrent(kind){
    const tr = lastSelectedRow() || tbody.querySelector('tr.pc-row');
    if (!tr) return;
    if (kind === 'detail'){
      window.location.href = `/captures/${tr.dataset.id}/`;
    } else if (kind === 'doi_or_url'){
      const href = tr.dataset.doiUrl || tr.dataset.url;
      if (href) window.open(href, '_blank', 'noopener');
    }
  }
  function copyDoi(){
    const tr = lastSelectedRow(); if (!tr) return;
    const doi = tr.dataset.doi;
    if (!doi) return;
    navigator.clipboard?.writeText(doi).then(()=>{},()=>{});
  }
  window.addEventListener('keydown', (e) => {
    const tag = (e.target && (e.target.tagName || '')).toLowerCase();
    const typing = tag === 'input' || tag === 'textarea' || e.target.isContentEditable;
    if (!typing && e.key === '/') { e.preventDefault(); searchInput?.focus(); return; }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'a') { e.preventDefault(); tbody.querySelectorAll('tr.pc-row').forEach(tr => toggleRow(tr, true)); return; }
    if (!typing && (e.key === 'Delete' || e.key === 'Backspace') && selected.size) { e.preventDefault(); bulkBtn?.click(); return; }
    if (!typing && e.key === 'Escape') { e.preventDefault(); clearSelection(); hideMenu(); hideColMenu(); return; }
    if (!typing && (e.key.toLowerCase() === 'c')) { e.preventDefault(); colsBtn?.click(); return; }
    if (!typing && (e.key.toLowerCase() === 'i')) { e.preventDefault(); document.getElementById('z-toggle-right')?.click(); return; }
    if (!typing && (e.key === 'j' || e.key === 'J')) { e.preventDefault(); moveSelection(+1); return; }
    if (!typing && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); moveSelection(-1); return; }
    if (!typing && e.key === 'Enter') { e.preventDefault(); openCurrent('detail'); return; }
    if (!typing && (e.key.toLowerCase() === 'o')) { e.preventDefault(); openCurrent('doi_or_url'); return; }
    if (!typing && (e.key.toLowerCase() === 'y')) { e.preventDefault(); copyDoi(); return; }
  });

  // -------------------- Collections discovery (delegated) --------------------
  // (duplicate local helper removed — we now rely on the early wrapper which calls dom.js)
  //
  // Previously there was a second `function scanCollections(){...}` here that shadowed
  // the wrapper defined near the top of this file. That duplicate has been removed
  // to ensure a single source of truth (captures/library/dom.js).

  // -------------------- Assign helpers --------------------
  async function assignIdsToCollection(ids, colId, op) {
    if (!ids?.length || !colId) return;
    const fd = new FormData();
    fd.append('csrfmiddlewaretoken', csrfToken());
    fd.append('op', op);
    ids.forEach(id => fd.append('ids', id));
    const resp = await fetch(`/collections/${colId}/assign/`, {
      method: 'POST', body: fd, credentials: 'same-origin',
      headers: {'X-CSRFToken': csrfToken()}
    });
    if (resp.redirected) { window.location.href = resp.url; return; }
    if (resp.ok) { window.location.reload(); return; }
    alert(`${op === 'add' ? 'Add to' : 'Remove from'} collection failed (${resp.status}).`);
  }
  async function assign(op){
    const colId = assignSelect?.value;
    if (!colId) { alert('Pick a collection first.'); return; }
    if (!selected.size) { alert('Select rows to assign.'); return; }
    return assignIdsToCollection([...selected], colId, op);
  }
  assignAdd?.addEventListener('click', () => assign('add'));
  assignRemove?.addEventListener('click', () => assign('remove'));

  // --- Row context menu (cleaned to use canonical keepOnScreen via window.PCDOM) ---
  let menuEl = null, submenuAddEl = null, submenuRemoveEl = null;

  function ensureRowMenu() {
    if (menuEl) return;
    menuEl = document.createElement("div");
    menuEl.className = "pc-context";
    document.body.appendChild(menuEl);

    submenuAddEl = document.createElement("div");
    submenuAddEl.className = "pc-submenu";
    submenuRemoveEl = document.createElement("div");
    submenuRemoveEl.className = "pc-submenu";
    document.body.appendChild(submenuAddEl);
    document.body.appendChild(submenuRemoveEl);

    menuEl.addEventListener("mousemove", (e) => {
      const li = e.target.closest("[data-sub]");
      if (!li) { submenuAddEl.style.display = "none"; submenuRemoveEl.style.display = "none"; return; }
      const kind  = li.getAttribute("data-sub");
      const box   = menuEl.getBoundingClientRect();
      const liBox = li.getBoundingClientRect();
      const el    = (kind === "remove") ? submenuRemoveEl : submenuAddEl;
      const other = (kind === "remove") ? submenuAddEl : submenuRemoveEl;

      other.style.display = "none";
      el.style.display = "block";
      el.style.left = (box.right + 2) + "px";
      el.style.top  = liBox.top + "px";
      keepOnScreen(el); // uses window.PCDOM.keepOnScreen from the top-of-file bridge
    });

    menuEl.addEventListener("mouseleave", () => {
      submenuAddEl.style.display = "none";
      submenuRemoveEl.style.display = "none";
    });

    menuEl.addEventListener("click", onRowMenuClick);
    ["click","scroll","resize"].forEach(ev => window.addEventListener(ev, hideRowMenu, { passive:true }));
  }

  function populateSubmenu(el, op) {
    const cols = scanCollections();
    const html = cols.map(c =>
      `<div class="pc-subitem" data-col="${escapeHtml(c.id)}">${escapeHtml(c.label)}</div>`
    ).join("") || `<div class="pc-subitem disabled">(no collections)</div>`;
    el.innerHTML = html;

    el.onclick = (e) => {
      const d = e.target.closest(".pc-subitem");
      if (!d || d.classList.contains("disabled")) return;
      const ids = idsFromSelection();
      assignIdsToCollection(ids, d.getAttribute("data-col"), op).catch(()=>{});
      hideRowMenu();
    };
  }

  function onRowMenuClick(e) {
    const actEl = e.target.closest("[data-act]"); if (!actEl) return;
    const act = actEl.getAttribute("data-act");

    if (act === "open") {
      const tr = document.querySelector("#pc-body tr.pc-row[aria-selected='true']") || document.querySelector("#pc-body tr.pc-row");
      if (tr) window.location.href = `/captures/${tr.dataset.id}/`;
    } else if (act === "open-ext") {
      const tr = document.querySelector("#pc-body tr.pc-row[aria-selected='true']") || document.querySelector("#pc-body tr.pc-row");
      if (tr) {
        const href = tr.dataset.doiUrl || tr.dataset.url;
        if (href) window.open(href, "_blank", "noopener");
      }
    } else if (act === "copy-doi") {
      const tr = document.querySelector("#pc-body tr.pc-row[aria-selected='true']");
      if (tr?.dataset?.doi) navigator.clipboard?.writeText(tr.dataset.doi);
    } else if (act === "remove-here") {
      const curCol = currentCollectionId();
      if (!curCol) return;
      const ids = idsFromSelection();
      assignIdsToCollection(ids, curCol, "remove");
    } else if (act === "delete") {
      document.getElementById("pc-bulk-delete")?.click();
    }
    hideRowMenu();
  }

  function hideRowMenu() {
    if (menuEl) menuEl.style.display = "none";
    if (submenuAddEl) submenuAddEl.style.display = "none";
    if (submenuRemoveEl) submenuRemoveEl.style.display = "none";
  }

  function showRowMenu(x, y) {
    ensureRowMenu();
    const curCol = currentCollectionId();
    menuEl.innerHTML = `
      <ul class="pc-menu">
        <li data-act="open">Open</li>
        <li data-act="open-ext">Open DOI/URL</li>
        <li data-act="copy-doi">Copy DOI</li>
        <li class="sep"></li>
        <li class="has-sub" data-sub="add">Add to collection ▸</li>
        ${curCol ? `<li data-act="remove-here">Remove from this collection</li>` : `<li class="has-sub" data-sub="remove">Remove from collection ▸</li>`}
        <li class="sep"></li>
        <li class="danger" data-act="delete">Delete…</li>
      </ul>
    `;
    menuEl.style.display = "block";
    menuEl.style.left = x + "px";
    menuEl.style.top  = y + "px";
    populateSubmenu(submenuAddEl, "add");
    if (!currentCollectionId()) { populateSubmenu(submenuRemoveEl, "remove"); } else { submenuRemoveEl.style.display = "none"; }
    keepOnScreen(menuEl); // canonical helper
  }

 
  // -------------------- Drag & Drop to Collections --------------------
  function ensureRowsDraggable(){
    tbody.querySelectorAll('tr.pc-row').forEach(tr => {
      if (tr.getAttribute('draggable') !== 'true') tr.setAttribute('draggable', 'true');
    });
  }
  ensureRowsDraggable();

  // drag image (ghost with count)
  let ghostEl = null;
  function makeGhost(count){
    if (ghostEl) ghostEl.remove();
    const g = document.createElement('div');
    g.className = 'pc-drag-ghost';
    g.textContent = `${count} selected`;
    document.body.appendChild(g);
    ghostEl = g;
    return g;
  }

  tbody.addEventListener('dragstart', (e) => {
    const tr = e.target.closest('tr.pc-row'); if (!tr) return;
    // If starting drag on an unselected row, select only that row
    if (tr.getAttribute('aria-selected') !== 'true') {
      clearSelection(); toggleRow(tr, true);
    }
    const ids = [...selected];
    e.dataTransfer.effectAllowed = 'copyMove';
    const payload = JSON.stringify({type:'pc-ids', ids});
    e.dataTransfer.setData('text/plain', payload);
    e.dataTransfer.setData('application/json', payload);
    const g = makeGhost(ids.length);
    e.dataTransfer.setDragImage(g, 10, 10);
    document.body.classList.add('pc-dragging');
  });
  tbody.addEventListener('dragend', () => {
    document.body.classList.remove('pc-dragging');
    ghostEl?.remove(); ghostEl = null;
  });

  function addDndHandlers(el, colId){
    el.addEventListener('dragenter', (e) => { e.preventDefault(); el.classList.add('dnd-over'); });
    el.addEventListener('dragover',  (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
    el.addEventListener('dragleave', () => { el.classList.remove('dnd-over'); });
    el.addEventListener('drop', async (e) => {
      e.preventDefault();
      e.stopPropagation(); // prevent link navigation on drop
      el.classList.remove('dnd-over');
      try{
        const data = e.dataTransfer.getData('text/plain') || e.dataTransfer.getData('application/json');
        let obj = {};
        try { obj = JSON.parse(data || '{}'); } catch(_){}
        const ids = (obj.type === 'pc-ids' && Array.isArray(obj.ids) && obj.ids.length) ? obj.ids : [...selected];
        if (ids.length){
          await assignIdsToCollection(ids, colId, 'add');
        }
      }catch(err){ console.warn(err); }
    });
  }

  function wireCollectionsDnd(){
    const cols = scanCollections();
    cols.forEach(({el, id}) => addDndHandlers(el, id));
  }
  wireCollectionsDnd();

  // -------------------- Collapsible groups (+ remember state) --------------------
  (function initGroups(){
    document.querySelectorAll('.z-group').forEach((g, idx) => {
      const key = g.getAttribute('data-key') || ('grp-' + idx);
      const title = g.querySelector('.z-group-title');
      if (!title) return;
      const saved = localStorage.getItem('pc-collapse:' + key);
      if (saved === '1') g.classList.add('collapsed');
      title.addEventListener('click', () => {
        const on = g.classList.toggle('collapsed');
        try { localStorage.setItem('pc-collapse:' + key, on ? '1' : '0'); } catch(_){}
      });
    });
  })();

  // -------------------- Simple modal (new / rename collection) --------------------
  const modalEl = document.getElementById('pc-modal');
  const modalTitle = document.getElementById('pc-modal-title');
  const modalInput = document.getElementById('pc-modal-input');
  const modalCancel= document.getElementById('pc-modal-cancel');
  const modalSubmit= document.getElementById('pc-modal-submit');

  let modalHandler = null;
  function openModal({title, placeholder, initial, submitText, onSubmit}){
    modalTitle.textContent = title || 'Input';
    modalInput.placeholder = placeholder || '';
    modalInput.value = initial || '';
    modalSubmit.textContent = submitText || 'OK';
    modalHandler = onSubmit || null;

    // UX: disable primary until there’s a value; Enter submits
    function syncDisabled() {
      modalSubmit.disabled = !(modalInput.value.trim().length > 0);
    }
    modalInput.removeEventListener('input', syncDisabled); // guard against duplicates
    modalInput.addEventListener('input', syncDisabled);
    modalInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !modalSubmit.disabled) modalSubmit.click();
    });
    syncDisabled();

    modalEl.style.display = 'flex';
    modalEl.setAttribute('aria-hidden', 'false');
    setTimeout(() => modalInput.focus(), 0);
  }

  function closeModal(){
    modalEl.style.display = 'none';
    modalEl.setAttribute('aria-hidden', 'true');
    modalHandler = null;
  }
  modalCancel?.addEventListener('click', closeModal);
  modalEl?.addEventListener('click', (e) => { if (e.target === modalEl) closeModal(); });
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modalEl?.style.display === 'flex') closeModal(); });
  modalSubmit?.addEventListener('click', async () => {
    if (!modalHandler) { closeModal(); return; }
    const v = modalInput.value.trim();
    const ok = await modalHandler(v);
    if (ok !== false) closeModal();
  });

  async function createCollection(name, parentId=null){
    if (!name) return false;
    const fd = new FormData();
    fd.append('csrfmiddlewaretoken', csrfToken());
    fd.append('name', name);
    if (parentId) fd.append('parent', parentId);
    const resp = await fetch('/collections/create/', {
      method:'POST', body: fd, credentials:'same-origin',
      headers: {'X-CSRFToken': csrfToken()}
    });
    if (resp.redirected) { window.location.href = resp.url; return true; }
    if (resp.ok) { window.location.reload(); return true; }
    alert('Create failed (' + resp.status + ').'); return false;
  }
  async function renameCollection(id, name){
    if (!id || !name) return false;
    const fd = new FormData();
    fd.append('csrfmiddlewaretoken', csrfToken());
    fd.append('name', name);
    const resp = await fetch(`/collections/${id}/rename/`, {
      method:'POST', body: fd, credentials:'same-origin',
      headers: {'X-CSRFToken': csrfToken()}
    });
    if (resp.redirected) { window.location.href = resp.url; return true; }
    if (resp.ok) { window.location.reload(); return true; }
    alert('Rename failed (' + resp.status + ').'); return false;
  }
  async function deleteCollection(id){
    if (!id) return false;
    const fd = new FormData();
    fd.append('csrfmiddlewaretoken', csrfToken());
    const resp = await fetch(`/collections/${id}/delete/`, {
      method:'POST', body: fd, credentials:'same-origin',
      headers: {'X-CSRFToken': csrfToken()}
    });
    if (resp.redirected) { window.location.href = resp.url; return true; }
    if (resp.ok) { window.location.reload(); return true; }
    alert('Delete failed (' + resp.status + ').'); return false;
  }

  // “+” button → new collection modal
  colAddBtn?.addEventListener('click', () => {
    openModal({
      title: 'New collection',
      placeholder: 'Name',
      submitText: 'Create',
      onSubmit: (val) => createCollection(val)
    });
  });

  // -------------------- Right-click on Collections (rename/delete) --------------------
  let colMenuEl = null, colMenuTarget = null;

  function ensureColMenu(){
    if (colMenuEl) return;
    colMenuEl = document.createElement('div');
    colMenuEl.className = 'pc-context';
    colMenuEl.innerHTML = `
      <ul class="pc-menu">
        <li data-act="open">Open</li>
        <li data-act="rename">Rename…</li>
        <li class="danger" data-act="delete">Delete…</li>
      </ul>
    `;
    document.body.appendChild(colMenuEl);
    colMenuEl.addEventListener('click', onColMenuClick);

    // Close on any outside click/scroll/resize
    window.addEventListener('click', (e) => { if (!colMenuEl.contains(e.target)) hideColMenu(); });
    window.addEventListener('scroll', hideColMenu, { passive: true });
    window.addEventListener('resize', hideColMenu);
  }

  function onColMenuClick(e){
    const a = colMenuTarget;
    if (!a) return hideColMenu();
    const id = a.getAttribute('data-collection-id');
    const label = (a.querySelector('.z-label')?.textContent || '').trim();
    const act = e.target.closest('[data-act]')?.getAttribute('data-act');
    if (!act) return;

    if (act === 'open') {
      window.location.href = a.href;
    } else if (act === 'rename') {
      openModal({
        title: 'Rename collection',
        initial: label,
        submitText: 'Save',
        onSubmit: (val) => renameCollection(id, val)
      });
    } else if (act === 'delete') {
      if (confirm(`Delete collection “${label}”? Items remain in All items.`)) {
        deleteCollection(id);
      }
    }
    hideColMenu();
  }

  function showColMenu(x, y, target){
    ensureColMenu();
    colMenuTarget = target;
    colMenuEl.style.display = 'block';
    colMenuEl.style.left = x + 'px';
    colMenuEl.style.top  = y + 'px';
    keepOnScreen(colMenuEl);
  }

  function hideColMenu(){
    if (colMenuEl) colMenuEl.style.display = 'none';
    colMenuTarget = null;
  }

  // Bind on the entire left rail; find the nearest collection link.
  zLeft?.addEventListener('contextmenu', (e) => {
    const link = e.target.closest('.z-link[data-collection-id]');
    if (!link) return;
    e.preventDefault();
    e.stopPropagation();
    showColMenu(e.pageX, e.pageY, link);
  });


  // -------------------- Apply saved column prefs on first load --------------------
  applyCols(readCols());
})();
