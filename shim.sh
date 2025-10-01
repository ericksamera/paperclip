#!/usr/bin/env bash
set -euo pipefail

git switch -c chore/stage-1-retire-selection-harden || true

SHIM=services/server/paperclip/static/captures/selection_harden.js
TEMPLATE_ROOT=services/server

# 1) Replace the legacy shim with a safe, inert compatibility file
mkdir -p "$(dirname "$SHIM")"
cat > "$SHIM" <<'JS'
/**
 * selection_harden.js — retired
 * This file is intentionally inert. It keeps legacy includes from breaking,
 * and offers minimal pass-through helpers to existing selection behavior.
 */
(() => {
  if (window.__PC_SELECTION_HARDEN_RETIRED) return;
  window.__PC_SELECTION_HARDEN_RETIRED = true;

  // Minimal, safe helpers in case anything calls into this shim.
  function getRows() {
    const tbody = document.querySelector('#z-table tbody') || document.querySelector('tbody');
    if (!tbody) return [];
    return Array.from(tbody.querySelectorAll('tr.pc-row, tr[data-row="pc-row"]'));
  }
  function getSelected(rows) {
    const el =
      document.querySelector('tr.pc-row.is-selected') ||
      document.querySelector('tr.pc-row.selected') ||
      document.querySelector('tr.pc-row[aria-selected="true"]') ||
      document.querySelector('tr[data-selected="true"]');
    const idx = el ? rows.indexOf(el) : -1;
    return { el, idx };
  }
  function move(delta) {
    const rows = getRows();
    if (!rows.length) return;
    const { el, idx } = getSelected(rows);
    let nextIdx = idx >= 0 ? idx + delta : (delta > 0 ? 0 : rows.length - 1);
    nextIdx = Math.max(0, Math.min(rows.length - 1, nextIdx));
    const next = rows[nextIdx];
    if (!next || next === el) return;
    try { next.scrollIntoView({ block: 'nearest' }); } catch {}
    next.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    next.setAttribute('tabindex', '-1');
    try { next.focus({ preventScroll: true }); } catch {}
  }

  // Provide a tiny global surface for any lingering callers.
  window.PCSelection = window.PCSelection || Object.freeze({
    selectRow: (el) => {
      if (!el) return;
      try { el.scrollIntoView({ block: 'nearest' }); } catch {}
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    },
    next: () => move(+1),
    prev: () => move(-1),
  });

  try {
    console.info("[paperclip] selection_harden.js loaded (retired shim, no-op).");
  } catch {}
})();
JS

# 2) Comment out any template includes of selection_harden.js
python3 - <<'PY'
import re, pathlib, sys

root = pathlib.Path("services/server")
templates = list(root.rglob("templates/**/*.html")) + list(root.rglob("templates/*.html"))
changed = []

pattern = re.compile(r'(<script[^>]+selection_harden\.js[^>]*>\s*</script>)', re.IGNORECASE)

for p in templates:
    try:
        s = p.read_text(encoding="utf-8")
    except Exception:
        continue
    s2 = pattern.sub(r'<!-- retired: \1 -->', s)
    if s2 != s:
        p.write_text(s2, encoding="utf-8")
        changed.append(str(p))

print("Commented out selection_harden.js in:")
for c in changed:
    print(" -", c)
PY

# 3) JS syntax check (just to be safe)
if command -v node >/dev/null 2>&1; then
  find services/server/paperclip/static -type f -name "*.js" -print0 | xargs -0 -n1 node --check
fi

# 4) Commit
git add -A
git commit -m "Stage 1: retire selection_harden.js (inert shim) and comment out any template includes" || true

echo
echo "✅ selection_harden.js retired safely."
echo "Now hard-reload /library (disable cache) and verify click + j/k still work."
