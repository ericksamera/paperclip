#!/usr/bin/env bash
set -euo pipefail

git switch -c chore/stage-1-listener-upgrade || true

python3 - <<'PY'
import re, pathlib

root = pathlib.Path("services/server/paperclip/static/captures")
js_files = [p for p in root.rglob("*.js")]

def add_rows_changed_listener(src: str) -> str:
    # For lines like: document.addEventListener('pc:rows-updated', handler
    # we append an adjacent listener for 'pc:rows-changed' using the same handler when the handler is a named identifier.
    pattern = re.compile(r"(document\.addEventListener\(\s*['\"]pc:rows-(?:updated|replaced)['\"]\s*,\s*)([A-Za-z_$][\w$]*)", re.M)
    def repl(m):
        prefix, handler = m.groups()
        return m.group(0) + f"\n{prefix}'pc:rows-changed', {handler}"
    return pattern.sub(repl, src)

changed = []
for p in js_files:
    s = p.read_text(encoding="utf-8")
    s2 = add_rows_changed_listener(s)
    if s2 != s:
        p.write_text(s2, encoding="utf-8")
        changed.append(str(p))

print("Upgraded listeners in:")
for c in changed:
    print(" -", c)
PY

# Syntax check again
if command -v node >/dev/null 2>&1; then
  find services/server/paperclip/static -type f -name "*.js" -print0 | xargs -0 -n1 node --check
fi

git add -A
git commit -m "Stage 1: add parallel 'pc:rows-changed' listeners where named handlers are used" || true

echo "✅ Listener upgrade done (non-breaking)."
