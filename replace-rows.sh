#!/usr/bin/env bash
set -euo pipefail

git switch -c chore/stage-1-rows-changed || true

# Choose a file that is definitely loaded on /library. Prefer selection.js; fallback to library.js.
TARGET=""
if [ -f services/server/paperclip/static/captures/library/selection.js ]; then
  TARGET=services/server/paperclip/static/captures/library/selection.js
elif [ -f services/server/paperclip/static/captures/library/library.js ]; then
  TARGET=services/server/paperclip/static/captures/library/library.js
else
  echo "❌ Could not find selection.js or library.js under static/captures/library/"
  exit 1
fi

echo "→ Appending rows-changed alias hub to: $TARGET"

cat >> "$TARGET" <<'JS'

// ===== Event alias hub: emit `pc:rows-changed` whenever legacy events fire =====
(() => {
  if (window.__pcRowsChangedAliased) return;
  window.__pcRowsChangedAliased = true;

  function reemit(detail) {
    try {
      document.dispatchEvent(new CustomEvent('pc:rows-changed', { detail }));
    } catch (_) {}
  }

  function makeHandler() {
    return (e) => reemit(e && e.detail);
  }

  // Listen to both legacy events and re-emit the canonical one.
  document.addEventListener('pc:rows-updated', makeHandler(), true);
  document.addEventListener('pc:rows-replaced', makeHandler(), true);
})();
/// ===== end alias hub =====
JS

# Syntax check just to be safe
if command -v node >/dev/null 2>&1; then
  node --check "$TARGET"
  find services/server/paperclip/static -type f -name "*.js" -print0 | xargs -0 -n1 node --check
fi

git add "$TARGET"
git commit -m "Stage 1: add rows-changed alias hub (keeps rows-updated/replaced; non-breaking)"

echo "✅ rows-changed alias in place. Hard-reload /library and continue."
