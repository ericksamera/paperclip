#!/usr/bin/env bash
set -euo pipefail

git switch -c chore/stage-1-audit || true

python3 - <<'PY'
import os, re, pathlib, json, textwrap
root = pathlib.Path(".")

def list_files(patterns):
    out = []
    for pat in patterns:
        out += [str(p) for p in root.glob(pat)]
    return sorted(out)

def grep(pattern, paths):
    rx = re.compile(pattern)
    hits = []
    for p in paths:
        try:
            s = pathlib.Path(p).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(s.splitlines(), 1):
            if rx.search(line):
                hits.append((p, i, line.strip()))
    return hits

static_js = [str(p) for p in pathlib.Path("services/server/paperclip/static").rglob("*.js")]
templates = [str(p) for p in pathlib.Path("services/server").rglob("templates/**/*.html")]
templates += [str(p) for p in pathlib.Path("services/server").rglob("templates/*.html")]

report = []
def add(title, lines):
    report.append("## " + title + "\n" + "\n".join(lines) + "\n")

# 1) Duplicates: details_panel.js
details_files = [p for p in static_js if p.endswith("/library/details_panel.js")]
add("Duplicate details_panel.js", [
    f"- {p}" for p in details_files
] or ["- none found"])

# 2) Legacy selection_harden.js
sel_harden = [p for p in static_js if p.endswith("selection_harden.js")]
add("Legacy selection_harden.js", [f"- {p}" for p in sel_harden] or ["- none found"])

# 3) Template includes of library.toolbar.js
toolbar_hits = grep(r'library\.toolbar\.js', [str(p) for p in pathlib.Path("services/server").rglob("templates/**/*.html")])
add("Template includes of library.toolbar.js", [
    f"- {p}:{ln}  {code}" for (p, ln, code) in toolbar_hits
] or ["- none found"])

# 4) Event names drift
ev_updated = grep(r'pc:rows-updated', static_js)
ev_replaced = grep(r'pc:rows-replaced', static_js)
ev_changed  = grep(r'pc:rows-changed', static_js)
add("Row events in JS", [
    f"- rows-updated   : {len(ev_updated)} occurrences",
    f"- rows-replaced  : {len(ev_replaced)} occurrences",
    f"- rows-changed   : {len(ev_changed)} occurrences",
])

# 5) Toast usage pathways
toast_global = grep(r'window\.Toast\.show|Toast\.show', static_js)
toast_dom = grep(r'\bdom\.toast\(|\bPCDOM\.toast\(', static_js)
add("Toast usage", [
    f"- Global Toast.show occurrences: {len(toast_global)}",
    f"- DOM helper toast() occurrences: {len(toast_dom)}",
])

# 6) DOM helper surface (PCDOM)
pcdom_exports = grep(r'window\.PCDOM|export\s+function\s+\w+', [p for p in static_js if "/library/dom.js" in p])
add("DOM helpers (dom.js)", [
    f"- {p}:{ln}  {code}" for (p, ln, code) in pcdom_exports
] or ["- dom.js not found"])

# Write report
out = pathlib.Path("docs/REFactor_STAGE1_AUDIT.md")
out.write_text("# Stage-1 Audit (Front-end consolidation)\n\n" + "\n".join(report), encoding="utf-8")
print(f"Wrote {out}")
PY

git add docs/REFactor_STAGE1_AUDIT.md
git commit -m "Stage 1 audit: write docs/REFactor_STAGE1_AUDIT.md (read-only findings)" || true

echo
echo "✅ Audit report written to docs/REFactor_STAGE1_AUDIT.md"
echo "Open it and tell me which items you want to tackle first (still non-breaking)."
