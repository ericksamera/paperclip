/**
 * selection_harden.js — robust legacy binder (click + j/k + arrows)
 * - Idempotent (guards against double-binding)
 * - Plays nice with ESM selection by simulating clicks (lets existing logic run)
 */
(() => {
  if (window.__pcLegacySelBound) return;
  window.__pcLegacySelBound = true;

  function isEditable(el) {
    if (!el) return false;
    if (el.isContentEditable) return true;
    const t = el.tagName;
    return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT';
  }

  function tbody() {
    return document.querySelector('#z-table tbody') ||
           document.getElementById('pc-body') ||
           document.querySelector('.pc-table tbody') ||
           document.querySelector('tbody');
  }

  function rows() {
    const tb = tbody();
    return tb ? Array.from(tb.querySelectorAll('tr.pc-row, tr[data-row="pc-row"], tr')) : [];
  }

  function current() {
    const el = document.querySelector('tr.pc-row.is-selected, tr.pc-row.selected, tr.pc-row[aria-selected="true"], tr[data-selected="true"]');
    return el;
  }

  function simulateClick(tr) {
    if (!tr) return;
    tr.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    // If selection classes/aria weren't set by any listener, set a minimal selection for UX
    if (!tr.classList.contains('is-selected') &&
        !tr.classList.contains('selected') &&
        tr.getAttribute('aria-selected') !== 'true') {
      tr.classList.add('selected');
      tr.setAttribute('aria-selected', 'true');
    }
  }

  function move(delta) {
    const list = rows();
    if (!list.length) return;
    const cur = current();
    let idx = cur ? list.indexOf(cur) : -1;
    let next = idx >= 0 ? idx + delta : (delta > 0 ? 0 : list.length - 1);
    next = Math.max(0, Math.min(list.length - 1, next));
    const tr = list[next];
    try { tr.scrollIntoView({ block: 'nearest' }); } catch {}
    simulateClick(tr);
    tr.setAttribute('tabindex','-1');
    try { tr.focus({ preventScroll: true }); } catch {}
  }

  function onKeydown(e) {
    if (e.defaultPrevented) return;
    if (isEditable(e.target) || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); move(+1); }
    else if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
  }

  function onClick(e) {
    const tb = tbody();
    if (!tb) return;
    const tr = e.target && e.target.closest && e.target.closest('tr');
    if (!tr || !tb.contains(tr)) return;
    if (isEditable(e.target)) return;
    // Avoid fighting with native link clicks inside the row; let default happen then re-select
    simulateClick(tr);
  }

  function bind() {
    document.addEventListener('keydown', onKeydown, true);
    document.addEventListener('click', onClick, true);
    try { console.info('[paperclip] selection_harden bound (legacy binder active).'); } catch {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind, { once: true });
  } else {
    bind();
  }
})();
