#!/usr/bin/env bash
set -euo pipefail

git switch -c chore/stage-1-remove-toolbar-include || true

TEMPLATE="services/server/paperclip/templates/captures/list.html"

# 1) Ensure template exists
test -f "$TEMPLATE" || { echo "❌ Missing: $TEMPLATE"; exit 1; }

# 2) Replace the script tag with an HTML comment (document the removal)
python3 - <<'PY'
import re, pathlib, sys
p = pathlib.Path("services/server/paperclip/templates/captures/list.html")
s = p.read_text(encoding="utf-8")

# Match any <script ...library.toolbar.js...></script> even with extra attrs/whitespace
rx = re.compile(r"""<script[^>]*library\.toolbar\.js[^>]*>\s*</script>""", re.IGNORECASE)
if rx.search(s):
    s2 = rx.sub(lambda m: f"<!-- removed legacy include: {m.group(0)} -->", s)
    p.write_text(s2, encoding="utf-8")
    print(f"Updated {p}")
else:
    print(f"No toolbar <script> tag found in {p} (already removed?)")
PY

# 3) Double-check there are no other references in templates
echo "— scanning for any remaining references to library.toolbar.js —"
git grep -n "library\.toolbar\.js" -- "services/server/paperclip/templates" || true

# 4) Quick JS syntax gate (unchanged code, but fast & safe)
if command -v node >/dev/null 2>&1; then
  find services/server/paperclip/static -type f -name "*.js" -print0 | xargs -0 -n1 node --check
fi

# 6) Commit
git add -A
git commit -m "Stage 1: remove <script> include for library.toolbar.js from captures/list.html (shim kept on disk)" || true

echo
echo "✅ Removed toolbar include."
echo "Next steps:"
echo "  • Hard-reload /library (DevTools → Network → Disable cache → Reload)."
echo "  • Click a row; details should fill. Press j/k or ↑/↓; selection should move."
echo "  • Push branch:  git push -u origin chore/stage-1-remove-toolbar-include"
