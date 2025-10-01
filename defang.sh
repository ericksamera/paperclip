#!/usr/bin/env bash
set -euo pipefail

git switch -c chore/stage-1-defang-toolbar || true

TOOLBAR="services/server/paperclip/static/captures/library.toolbar.js"
BACKUP="services/server/paperclip/static/captures/library.toolbar.legacy.js"

# 1) If toolbar exists, back it up
if [ -f "$TOOLBAR" ]; then
  cp -n "$TOOLBAR" "$BACKUP"
fi

# 2) Introspect likely global names (window.* and top-level function decls)
python3 - <<'PY'
import re, pathlib, json, sys
p = pathlib.Path("services/server/paperclip/static/captures/library.toolbar.js")
symbols = {"globals": set(), "funcs": set()}
if p.exists():
    s = p.read_text(encoding="utf-8", errors="ignore")
    # window.Foo = ..., window['Foo'] = ...
    for m in re.finditer(r"window\[['\"]([A-Za-z_$][\w$]*)['\"]\]\s*=", s): symbols["globals"].add(m.group(1))
    for m in re.finditer(r"window\.([A-Za-z_$][\w$]*)\s*=", s): symbols["globals"].add(m.group(1))
    # function Foo(...) { ... } at top level
    for m in re.finditer(r"^\s*function\s+([A-Za-z_$][\w$]*)\s*\(", s, flags=re.M): symbols["funcs"].add(m.group(1))
    # var/let/const Foo = function/() => ...
    for m in re.finditer(r"^\s*(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:function|\([^\)]*\)\s*=>)", s, flags=re.M):
        symbols["funcs"].add(m.group(1))
else:
    # If file is missing, still generate an empty shim
    pass

# Write a small JSON file so the shell script can read what we found (optional)
out = pathlib.Path("docs/.toolbar_symbols.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({k: sorted(list(v)) for k,v in symbols.items()}, indent=2), encoding="utf-8")
print(out)
PY

SYMS_JSON="docs/.toolbar_symbols.json"
echo "Symbols JSON at: $SYMS_JSON (informational)"

# 3) Generate a harmless shim that preserves any globals as no-ops
python3 - <<'PY'
import json, pathlib, sys
symbols_path = pathlib.Path("docs/.toolbar_symbols.json")
globals_syms = []
func_syms = []
if symbols_path.exists():
    data = json.loads(symbols_path.read_text(encoding="utf-8"))
    globals_syms = data.get("globals", [])
    func_syms = data.get("funcs", [])
# Build shim
lines = []
lines.append("/**")
lines.append(" * library.toolbar.js — defanged shim")
lines.append(" * This file intentionally provides no behavior; it preserves any expected globals as no-ops.")
lines.append(" * The modern ESM modules own the Library UI. This shim prevents ReferenceErrors while we remove legacy code.")
lines.append(" */")
lines.append("(function(){")
lines.append("  try { console.info('[paperclip] library.toolbar.js shim loaded'); } catch(e) {}")
for name in sorted(set(globals_syms + func_syms)):
    # Define the symbol on window if missing
    lines.append(f"  if (typeof window['{name}'] === 'undefined') window['{name}'] = function(){{}};")
lines.append("})();")
shim = "\n".join(lines)

target = pathlib.Path("services/server/paperclip/static/captures/library.toolbar.js")
target.write_text(shim, encoding="utf-8")
print(f"Wrote shim to {target}")
PY

# 4) Syntax check everything
if command -v node >/dev/null 2>&1; then
  find services/server/paperclip/static -type f -name "*.js" -print0 | xargs -0 -n1 node --check
fi

# 5) Commit
git add -A
git commit -m "Stage 1: defang library.toolbar.js into a no-op compatibility shim; backup original" || true

echo
echo "✅ Toolbar defanged safely."
echo "Hard-reload /library (disable cache) and confirm selection + j/k still work."
