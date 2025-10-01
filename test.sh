#!/usr/bin/env bash
set -euo pipefail

git switch -c fix/library-hotkeys || true

# Choose a target that’s definitely loaded on /library
TARGET=""
if [ -f services/server/paperclip/static/captures/library/selection.js ]; then
  TARGET=services/server/paperclip/static/captures/library/selection.js
elif [ -f services/server/paperclip/static/captures/library/library.js ]; then
  TARGET=services/server/paperclip/static/captures/library/library.js
else
  echo "❌ Could not find selection.js or library.js under static/captures/library/"
  exit 1
fi

echo "→ Appending hotkeys to: $TARGET"

cat >> "$TARGET" <<'JS'

// ===== Hotkeys: j/k and ArrowUp/ArrowDown for Library rows (safe, idempotent) =====
(() => {
  // Prevent double binding across reloads
  let __pcHotkeysBound = false;

  function isEditable(el) {
    if (!el) return false;
    if (el.isContentEditable) return true;
    const tag = el.tagName;
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
  }

  function getRows() {
    const tbody = document.querySelector('#z-table tbody') || document.querySelector('tbody');
    if (!tbody) return [];
    // support both modern and legacy row classes
    return Array.from(tbody.querySelectorAll('tr.pc-row, tr[data-row="pc-row"]'));
  }

  function getCurrent(rows) {
    // try common selected markers in order
    const candidate =
      document.querySelector('tr.pc-row.is-selected') ||
      document.querySelector('tr.pc-row.selected') ||
      document.querySelector('tr.pc-row[aria-selected="true"]') ||
      document.querySelector('tr[data-selected="true"]');
    if (!candidate) return { el: null, idx: -1 };
    const idx = rows.indexOf(candidate);
    return { el: candidate, idx };
  }

  function move(delta) {
    const rows = getRows();
    if (!rows.length) return;

    const { el: current, idx } = getCurrent(rows);
    let nextIdx = idx >= 0 ? idx + delta : (delta > 0 ? 0 : rows.length - 1);
    if (nextIdx < 0) nextIdx = 0;
    if (nextIdx >= rows.length) nextIdx = rows.length - 1;

    const next = rows[nextIdx];
    if (!next || next === current) return;

    // Scroll into view and simulate a click so existing selection logic runs
    try { next.scrollIntoView({ block: 'nearest' }); } catch {}
    next.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    // Also move focus for accessibility
    next.setAttribute('tabindex', '-1');
    try { next.focus({ preventScroll: true }); } catch {}
  }

  function onKeydown(e) {
    if (e.defaultPrevented) return;
    if (isEditable(e.target)) return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;

    const k = e.key;
    if (k === 'j' || k === 'ArrowDown') {
      e.preventDefault();
      move(+1);
    } else if (k === 'k' || k === 'ArrowUp') {
      e.preventDefault();
      move(-1);
    }
  }

  // Bind once on DOM ready
  function bind() {
    if (__pcHotkeysBound) return;
    __pcHotkeysBound = true;
    document.addEventListener('keydown', onKeydown, true);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind, { once: true });
  } else {
    bind();
  }
})();
/// ===== end hotkeys =====
JS

# Syntax check the modified file and all static JS
if command -v node >/dev/null 2>&1; then
  echo "— node --check $TARGET —"
  node --check "$TARGET"
  echo "— node --check all static JS —"
  find services/server/paperclip/static -type f -name "*.js" -print0 | xargs -0 -n1 node --check
else
  echo "⚠️ Node not found; skipping syntax check. (Your previous run suggested Node is installed.)"
fi

git add "$TARGET"
git commit -m "Library: restore j/k & arrow key navigation by simulating row click (hotkey binder)"

echo "✅ Hotkeys appended. Hard-reload the Library page (disable cache) and test j/k."
