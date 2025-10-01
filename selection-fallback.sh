#!/usr/bin/env bash
set -euo pipefail

git switch -c fix/selection-restore-working || true

SEL_JS="services/server/paperclip/static/captures/library/selection.js"
HARDEN_JS="services/server/paperclip/static/captures/selection_harden.js"

# 1) Ensure selection.js exists
if [ ! -f "$SEL_JS" ]; then
  echo "❌ $SEL_JS not found"; exit 1
fi

# 2) Append rows-changed alias hub if missing (non-breaking)
python3 - <<'PY'
import pathlib, re
p = pathlib.Path("services/server/paperclip/static/captures/library/selection.js")
s = p.read_text(encoding="utf-8")
if "Event alias hub: emit `pc:rows-changed`" not in s and "pc:rows-changed" not in s:
    s += """

// ===== Event alias hub: emit `pc:rows-changed` whenever legacy events fire =====
(() => {
  if (window.__pcRowsChangedAliased) return;
  window.__pcRowsChangedAliased = true;

  function reemit(detail) {
    try { document.dispatchEvent(new CustomEvent('pc:rows-changed', { detail })); } catch (_) {}
  }
  const handler = (e) => reemit(e && e.detail);
  document.addEventListener('pc:rows-updated', handler, true);
  document.addEventListener('pc:rows-replaced', handler, true);
})();
/// ===== end alias hub =====
"""
    p.write_text(s, encoding="utf-8")
    print("appended: rows-changed alias hub")
else:
    print("rows-changed alias already present")
PY

# 3) Append hotkeys binder to selection.js if missing (idempotent)
python3 - <<'PY'
import pathlib
p = pathlib.Path("services/server/paperclip/static/captures/library/selection.js")
s = p.read_text(encoding="utf-8")
if "===== Hotkeys: j/k and ArrowUp/ArrowDown for Library rows" not in s:
    s += """

// ===== Hotkeys: j/k and ArrowUp/ArrowDown for Library rows (safe, idempotent) =====
(() => {
  if (window.__pcHotkeysBound) return;
  window.__pcHotkeysBound = true;

  function isEditable(el) {
    if (!el) return false;
    if (el.isContentEditable) return true;
    const tag = el.tagName;
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
  }

  function getRows() {
    const tbody = document.querySelector('#z-table tbody') || document.querySelector('tbody');
    if (!tbody) return [];
    return Array.from(tbody.querySelectorAll('tr.pc-row, tr[data-row="pc-row"], tr'));
  }

  function getCurrent(rows) {
    const el = document.querySelector('tr.pc-row.is-selected, tr.pc-row.selected, tr.pc-row[aria-selected="true"], tr[data-selected="true"]');
    const idx = el ? rows.indexOf(el) : -1;
    return { el, idx };
  }

  function move(delta) {
    const rows = getRows();
    if (!rows.length) return;
    const { el, idx } = getCurrent(rows);
    let nextIdx = idx >= 0 ? idx + delta : (delta > 0 ? 0 : rows.length - 1);
    nextIdx = Math.max(0, Math.min(rows.length - 1, nextIdx));
    const next = rows[nextIdx];
    if (!next || next === el) return;
    try { next.scrollIntoView({ block: 'nearest' }); } catch {}
    // simulate click so existing selection logic runs
    next.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    next.setAttribute('tabindex', '-1');
    try { next.focus({ preventScroll: true }); } catch {}
  }

  function onKeydown(e) {
    if (e.defaultPrevented) return;
    if (isEditable(e.target)) return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const k = e.key;
    if (k === 'j' || k === 'ArrowDown') { e.preventDefault(); move(+1); }
    else if (k === 'k' || k === 'ArrowUp') { e.preventDefault(); move(-1); }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => document.addEventListener('keydown', onKeydown, true), { once: true });
  } else {
    document.addEventListener('keydown', onKeydown, true);
  }
})();
/// ===== end hotkeys =====
"""
    p.write_text(s, encoding="utf-8")
    print("appended: hotkeys binder")
else:
    print("hotkeys binder already present")
PY

# 4) Replace selection_harden.js with a robust click+hotkey binder with guards
mkdir -p "$(dirname "$HARDEN_JS")"
cat > "$HARDEN_JS" <<'JS'
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
JS

# 5) Syntax check all static JS
if command -v node >/dev/null 2>&1; then
  echo "— node --check selection + harden —"
  node --check "$SEL_JS"
  node --check "$HARDEN_JS"
  echo "— node --check entire static tree —"
  find services/server/paperclip/static -type f -name "*.js" -print0 | xargs -0 -n1 node --check
else
  echo "⚠️ Node not found; skipping syntax check."
fi

git add -A
git commit -m "Restore working selection: ensure hotkeys + rows-changed in selection.js; robust selection_harden binder (click + hotkeys)"
echo "✅ Done. Hard-reload /library (disable cache) and test click + j/k."
