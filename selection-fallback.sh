#!/usr/bin/env bash
set -euo pipefail

git switch -c fix/selection-fallback || true

# 1) Ensure ESM selection sets a global "ready" flag, so fallbacks no-op when ESM is active.
# Insert "window.__pcESMSelectionReady = true;" right after `_wired = true;` in initSelection().
python3 - <<'PY'
import re, pathlib, sys
p = pathlib.Path("services/server/paperclip/static/captures/library/selection.js")
s = p.read_text(encoding="utf-8")
pat = re.compile(r"(\b_wired\s*=\s*true;\s*)", re.M)
if not re.search(r"__pcESMSelectionReady", s):
    s2 = pat.sub(r"\1\n  try { window.__pcESMSelectionReady = true; } catch(_) {}\n", s, count=1)
    p.write_text(s2, encoding="utf-8")
    print("patched:", p)
else:
    print("already marked ready:", p)
PY

# 2) Replace selection_harden.js with a SAFE FALLBACK (binds only if ESM didn't wire).
cat > services/server/paperclip/static/captures/selection_harden.js <<'JS'
/**
 * selection_harden.js — Fallback-only selection binder.
 * Loads on pages that still include it. If the ESM selection has wired (window.__pcESMSelectionReady),
 * this file is inert. Otherwise it provides click + j/k/arrow selection by simulating row clicks.
 */
(() => {
  if (window.__PC_SELECTION_HARDEN_FALLBACK__) return;
  window.__PC_SELECTION_HARDEN_FALLBACK__ = true;

  function isEditable(el) {
    if (!el) return false;
    if (el.isContentEditable) return true;
    const t = el.tagName;
    return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT';
  }

  function tbody() {
    return document.getElementById('pc-body') ||
           document.querySelector('.pc-table tbody') ||
           document.querySelector('#z-table tbody') ||
           document.querySelector('tbody');
  }

  function rows() {
    const tb = tbody();
    return tb ? Array.from(tb.querySelectorAll('tr.pc-row, tr[data-row="pc-row"], tr')) : [];
  }

  function currentIdx(list) {
    const el = document.querySelector('tr.pc-row.is-selected, tr.pc-row.selected, tr.pc-row[aria-selected="true"], tr[data-selected="true"]');
    return el ? list.indexOf(el) : -1;
  }

  function ensureRowShape() {
    const tb = tbody();
    if (!tb) return;
    tb.querySelectorAll('tr').forEach(tr => {
      tr.classList.add('pc-row');
      if (!tr.hasAttribute('aria-selected')) tr.setAttribute('aria-selected', 'false');
    });
  }

  function clickSelect(tr) {
    if (!tr) return;
    // Let existing selection logic (if any) handle it first.
    tr.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    // If nothing handled it, toggle ARIA/legacy class as a last resort.
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
    let idx = currentIdx(list);
    let next = idx >= 0 ? idx + delta : (delta > 0 ? 0 : list.length - 1);
    if (next < 0) next = 0;
    if (next >= list.length) next = list.length - 1;
    const tr = list[next];
    try { tr.scrollIntoView({ block: 'nearest' }); } catch {}
    clickSelect(tr);
    tr.setAttribute('tabindex','-1');
    try { tr.focus({ preventScroll: true }); } catch {}
  }

  function onKeydown(e) {
    if (window.__pcESMSelectionReady) return;        // ESM owns keys
    if (e.defaultPrevented) return;
    if (isEditable(e.target) || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); move(+1); }
    else if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
  }

  function onClick(e) {
    if (window.__pcESMSelectionReady) return;        // ESM owns clicks
    const tb = tbody();
    if (!tb) return;
    const tr = e.target && e.target.closest && e.target.closest('tr');
    if (!tr || !tb.contains(tr)) return;
    if (isEditable(e.target)) return;
    clickSelect(tr);
  }

  function bind() {
    if (window.__pcESMSelectionReady) {
      try { console.info('[paperclip] selection_harden fallback: ESM active, inert.'); } catch {}
      return;
    }
    ensureRowShape();
    document.addEventListener('keydown', onKeydown, true);
    document.addEventListener('click', onClick, true);
    try { console.info('[paperclip] selection_harden fallback bound.'); } catch {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind, { once: true });
  } else {
    bind();
  }

  // tiny global for any legacy code
  window.PCSelection = window.PCSelection || Object.freeze({
    next: () => move(+1),
    prev: () => move(-1),
    selectRow: (el) => el && clickSelect(el),
  });
})();
JS

# 3) Un-comment any template includes we auto-commented (restore them)
python3 - <<'PY'
import re, pathlib
root = pathlib.Path("services/server")
templates = list(root.rglob("templates/**/*.html")) + list(root.rglob("templates/*.html"))
changed = []
for p in templates:
    s = p.read_text(encoding="utf-8", errors="ignore")
    s2 = re.sub(r'<!--\s*retired:\s*(<script[^>]+selection_harden\.js[^>]*>\s*</script>)\s*-->', r'\1', s, flags=re.IGNORECASE)
    if s2 != s:
        p.write_text(s2, encoding="utf-8")
        changed.append(str(p))
print("restored in:", *changed, sep="\n - " if changed else "\n(none)")
PY

# 4) Syntax check JS
if command -v node >/dev/null 2>&1; then
  find services/server/paperclip/static -type f -name "*.js" -print0 | xargs -0 -n1 node --check
fi

# 5) Commit
git add -A
git commit -m "Selection: mark ESM ready flag and make selection_harden a fallback; restore template includes" || true

echo "✅ Fallback in place. Hard-reload /library (disable cache) and test click + j/k."
