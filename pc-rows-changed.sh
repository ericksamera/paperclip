#!/usr/bin/env bash
set -euo pipefail

git switch -c chore/stage-1-rows-changed-listeners || true

python3 - <<'PY'
import re, pathlib

root = pathlib.Path("services/server/paperclip/static/captures")
js_files = [p for p in root.rglob("*.js")]

# Only add a parallel listener when it's a named handler:
#   document.addEventListener('pc:rows-updated', someHandler)
# becomes:
#   document.addEventListener('pc:rows-updated', someHandler)
#   document.addEventListener('pc:rows-changed', someHandler)
pat = re.compile(r"(document\.addEventListener\(\s*['\"]pc:rows-(?:updated|replaced)['\"]\s*,\s*)([A-Za-z_$][\w$]*)", re.M)

changed = []
for p in js_files:
    s = p.read_text(encoding="utf-8")
    s2 = pat.sub(lambda m: m.group(0) + "\n" + m.group(1) + "'pc:rows-changed', " + m.group(2), s)
    if s2 != s:
        p.write_text(s2, encoding="utf-8")
        changed.append(str(p))

print("Upgraded listeners in:")
for c in changed:
    print(" -", c)
PY

# Syntax check (fast)
if command -v node >/dev/null 2>&1; then
  find services/server/paperclip/static -type f -name "*.js" -print0 | xargs -0 -n1 node --check
fi

git add -A
git commit -m "Stage 1: add parallel 'pc:rows-changed' listeners where named handlers are used" || true

echo "✅ Listener upgrade done (non-breaking)."
