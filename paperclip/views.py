from __future__ import annotations
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.html import escape
import re
from pathlib import Path
from .artifacts import get_artifact_dir
from .models import Capture

# Allow the new artifact
ALLOWED_ARTIFACTS = {"page.html", "raw_ingest.json", "parsed.json", "server_parsed.json"}

def artifact_download(_request, pk: str, basename: str):
    if basename not in ALLOWED_ARTIFACTS:
        raise Http404("Unknown artifact")
    path = get_artifact_dir(pk) / basename
    if not path.exists():
        raise Http404("Not found")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=basename)

# Optional: simple read-only preview
def view_capture(request, pk: str):
    cap = get_object_or_404(Capture, pk=pk)
    content = cap.content_html or ""
    content = re.sub(r"(?is)<script.*?>.*?</script>", "", content)
    content = re.sub(r"(?is)<style.*?>.*?</style>", "", content)
    refs = cap.references.all()[:3]
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>{escape(cap.title or cap.url)}</title>
    <style>
      body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
            max-width:860px;margin:32px auto;line-height:1.6;padding:0 16px}}
      .meta{{color:#555;margin-bottom:16px}}
      .counts span{{margin-right:12px}}
      hr{{margin:24px 0}}
    </style>
  </head>
  <body>
    <h1>{escape(cap.title or 'Untitled')}</h1>
    <div class="meta">
      <a href="{escape(cap.url)}">{escape(cap.url)}</a>
      <div class="counts">
        <span>Refs: {cap.references.count()}</span>
        <span>Figures: {len(cap.figures or [])}</span>
        <span>Tables: {len(cap.tables or [])}</span>
      </div>
      <div class="counts">
        <span>DOI: {escape(str((cap.meta or {}).get('doi') or '—'))}</span>
      </div>
    </div>
    <div id="content">{content}</div>
    <hr/>
    <h3>First 3 references</h3>
    <ol>
      {''.join(f"<li>{escape(r.apa or r.raw or '')}</li>" for r in refs)}
    </ol>
  </body>
</html>"""
    return HttpResponse(html)
