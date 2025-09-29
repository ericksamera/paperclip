// services/server/paperclip/static/captures/library.js
// Library polish: sticky tooling + chips + infinite scroll + hotkeys
// PLUS: right-click context menu + drag & drop to Collections.

(function () {
  const shell = document.getElementById('z-shell');
  const tbody = document.getElementById('pc-body');
  const zLeft = document.querySelector('.z-left');
  const zCenter = document.querySelector('.z-center');
  if (!shell || !tbody) return;

  // -------------------- helpers --------------------
  const selected = new Set();
  const bulkForm = document.getElementById('pc-bulk-form');
  const bulkBtn  = document.getElementById('pc-bulk-delete');

  const assignSelect = document.getElementById('pc-assign-select');
  const assignAdd    = document.getElementById('pc-assign-add');
  const assignRemove = document.getElementById('pc-assign-remove');

  const colsBtn    = document.getElementById('pc-cols-toggle');
  const colsPanel  = document.getElementById('pc-cols-panel');
  const colsClose  = document.getElementById('pc-cols-close');
  const colsReset  = document.getElementById('pc-cols-reset');

  const searchInput = document.querySelector('.z-search input[name=q]');

  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(^|; )' + name + '=([^;]*)'));
    return m ? decodeURIComponent(m[2]) : '';
  }
  function csrfToken() {
    return getCookie('csrftoken') ||
           (document.querySelector('input[name=csrfmiddlewaretoken]')?.value || '');
  }
  function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }
  function urlParamsObj() {
    const u = new URL(location.href);
    const o = {};
    u.searchParams.forEach((v, k) => { if (v !== '') o[k] = v; });
    return o;
  }
  function buildQs(next) {
    const u = new URL(location.href);
    const p = u.searchParams;
    Object.keys(next).forEach(k => {
      const v = next[k];
      if (v === null || v === undefined) p.delete(k);
      else p.set(k, String(v));
    });
    if (!('page' in next)) p.delete('page');
    return '?' + p.toString();
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

  bulkBtn?.addEventListener('click', async (e) => {
    e.preventDefault();
    if (!selected.size) return;
    if (!confirm(`Delete ${selected.size} selected item(s)?`)) return;
    try {
      const fd = new FormData();
      fd.append('csrfmiddlewaretoken', csrfToken());
      selected.forEach(id => fd.append('ids', id));
      const resp = await fetch(bulkForm.action, {
        method: 'POST', body: fd, credentials: 'same-origin',
        headers: {'X-CSRFToken': csrfToken()}
      });
      if (resp.redirected) { window.location.href = resp.url; return; }
      if (resp.ok) { window.location.reload(); return; }
      alert(`Delete failed (${resp.status}).`);
    } catch (err) {
      alert(`Delete failed.\n${String(err)}`);
    }
  });

  // -------------------- info panel + splitters --------------------
  const info = document.getElementById('z-info');
  const toggleRightBtn = document.getElementById('z-toggle-right');

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
  function openRight() { shell.style.setProperty('--right-w', localStorage.getItem('pc-right-w') || '360px'); }
  function closeRight() { shell.style.setProperty('--right-w', '0px'); }
  toggleRightBtn?.addEventListener('click', () => {
    const w = getComputedStyle(shell).getPropertyValue('--right-w').trim();
    if (w === '0px' || w === '0') openRight(); else closeRight();
  });
  makeSplitter('z-splitter-left', '--left-w', 160, 480, 'pc-left-w');
  makeSplitter('z-splitter-right', '--right-w', 0, 560, 'pc-right-w');
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
    const params = urlParamsObj();
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
    if (!typing && e.key === 'Escape') { e.preventDefault(); clearSelection(); hideMenu(); return; }
    if (!typing && (e.key.toLowerCase() === 'c')) { e.preventDefault(); colsBtn?.click(); return; }
    if (!typing && (e.key.toLowerCase() === 'i')) { e.preventDefault(); document.getElementById('z-toggle-right')?.click(); return; }
    if (!typing && (e.key === 'j' || e.key === 'J')) { e.preventDefault(); moveSelection(+1); return; }
    if (!typing && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); moveSelection(-1); return; }
    if (!typing && e.key === 'Enter') { e.preventDefault(); openCurrent('detail'); return; }
    if (!typing && (e.key.toLowerCase() === 'o')) { e.preventDefault(); openCurrent('doi_or_url'); return; }
    if (!typing && (e.key.toLowerCase() === 'y')) { e.preventDefault(); copyDoi(); return; }
  });

  // -------------------- Collections discovery --------------------
  function scanCollections() {
    if (!zLeft) return [];
    // Prefer explicit data-collection-id (we added it in list.html), then fall back to href parsing.
    const links = [...zLeft.querySelectorAll('[data-collection-id], a[href*="col="], a[href^="/collections/"]')];
    const list = [];
    links.forEach((a) => {
      let id = a.getAttribute('data-collection-id');
      if (!id) {
        try {
          const href = a.getAttribute('href') || '';
          if (href.includes('col=')) {
            const u = new URL(href, location.href);  // make relative-to-current-page robust
            id = u.searchParams.get('col');
          } else {
            const m = href.match(/\/collections\/([^/?#]+)/);
            if (m) id = m[1];
          }
        } catch(_) {}
      }
      const label = (a.querySelector('.z-label')?.textContent || a.textContent || '').trim();
      if (id && label && !/^(All items|New collection)$/i.test(label)) {
        a.dataset.collectionId = id;
        list.push({ id, label, el: a });
      }
    });
    return list;
  }

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

  // -------------------- Context menu --------------------
  let menuEl = null, submenuEl = null, submenuRemoveEl = null;
  function ensureMenu() {
    if (menuEl) return;
    menuEl = document.createElement('div');
    menuEl.className = 'pc-context';
    menuEl.innerHTML = `
      <ul class="pc-menu">
        <li data-act="open">Open</li>
        <li data-act="open-ext">Open DOI/URL</li>
        <li data-act="copy-doi">Copy DOI</li>
        <li class="sep"></li>
        <li class="has-sub" data-sub="add">Add to collection ▸</li>
        <li class="has-sub" data-sub="remove">Remove from collection ▸</li>
        <li class="sep"></li>
        <li class="danger" data-act="delete">Delete…</li>
      </ul>
    `;
    document.body.appendChild(menuEl);

    submenuEl = document.createElement('div');          // add
    submenuEl.className = 'pc-submenu';
    submenuRemoveEl = document.createElement('div');    // remove
    submenuRemoveEl.className = 'pc-submenu';
    document.body.appendChild(submenuEl);
    document.body.appendChild(submenuRemoveEl);

    menuEl.addEventListener('mousemove', (e) => {
      const li = e.target.closest('[data-sub]');
      if (!li) { hideSubmenus(); return; }
      const kind = li.getAttribute('data-sub');
      showSubmenu(kind, menuEl.getBoundingClientRect().right + 2, li.getBoundingClientRect().top);
    });
    menuEl.addEventListener('mouseleave', hideSubmenus);
    menuEl.addEventListener('click', onMenuClick);
  }
  function populateSubmenu(el, op) {
    const cols = scanCollections();
    const html = cols.map(c => `<div class="pc-subitem" data-col="${escapeHtml(c.id)}">${escapeHtml(c.label)}</div>`).join('') || '<div class="pc-subitem disabled">(no collections)</div>';
    el.innerHTML = html;
    el.onclick = (e) => {
      const d = e.target.closest('.pc-subitem'); if (!d || d.classList.contains('disabled')) return;
      const ids = [...selected];
      assignIdsToCollection(ids, d.getAttribute('data-col'), op).catch(()=>{});
      hideMenu();
    };
  }
  function onMenuClick(e) {
    const actEl = e.target.closest('[data-act]'); if (!actEl) return;
    const act = actEl.getAttribute('data-act');
    if (act === 'open') openCurrent('detail');
    else if (act === 'open-ext') openCurrent('doi_or_url');
    else if (act === 'copy-doi') copyDoi();
    else if (act === 'delete') bulkBtn?.click();
    hideMenu();
  }
  function showMenu(x, y) {
    ensureMenu();
    menuEl.style.display = 'block';
    menuEl.style.left = x + 'px';
    menuEl.style.top = y + 'px';
    populateSubmenu(submenuEl, 'add');
    populateSubmenu(submenuRemoveEl, 'remove');
    keepOnScreen(menuEl);
  }
  function hideMenu() {
    if (menuEl) menuEl.style.display = 'none';
    hideSubmenus();
  }
  function hideSubmenus(){
    submenuEl.style.display = 'none';
    submenuRemoveEl.style.display = 'none';
  }
  function showSubmenu(which, x, y){
    const el = (which === 'remove') ? submenuRemoveEl : submenuEl;
    el.style.display = 'block';
    el.style.left = x + 'px';
    el.style.top = y + 'px';
    keepOnScreen(el);
  }
  function keepOnScreen(el){
    const r = el.getBoundingClientRect();
    let nx = r.left, ny = r.top, changed = false;
    if (r.right > window.innerWidth) { nx = Math.max(8, window.innerWidth - r.width - 8); changed = true; }
    if (r.bottom > window.innerHeight) { ny = Math.max(8, window.innerHeight - r.height - 8); changed = true; }
    if (changed) { el.style.left = nx + 'px'; el.style.top = ny + 'px'; }
  }

  tbody.addEventListener('contextmenu', (e) => {
    const tr = e.target.closest('tr.pc-row');
    if (!tr) return;
    e.preventDefault();
    // if right-clicking a non-selected row, select only it
    if (tr.getAttribute('aria-selected') !== 'true') {
      clearSelection();
      toggleRow(tr, true);
    }
    showMenu(e.pageX, e.pageY);
  });
  window.addEventListener('click', (e) => {
    if (!menuEl) return;
    if (!menuEl.contains(e.target) && !submenuEl.contains(e.target) && !submenuRemoveEl.contains(e.target)) hideMenu();
  });
  window.addEventListener('scroll', hideMenu, { passive: true });
  window.addEventListener('resize', hideMenu);

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
    e.dataTransfer.setData('application/json', payload);            // extra type for some browsers
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

  // -------------------- Apply saved column prefs on first load --------------------
  applyCols(readCols());
})();
