# Paperclip

Local tool to capture web papers/articles, parse them into clean text + sections + references, and export in a few useful formats.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open:

- Library: [http://127.0.0.1:8000/library/](http://127.0.0.1:8000/library/)
- Collections: [http://127.0.0.1:8000/collections/](http://127.0.0.1:8000/collections/)

## Chrome extension

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. **Load unpacked** → select `extensions/chrome/`

If your server isn’t on `http://127.0.0.1:8000`, edit `API_ENDPOINT` in the corresponding extension's `background.js`.

## Firefox extension

1. Open `about:debugging#/runtime/this-firefox` in Firefox.
2. Click **Load Temporary Add-on…** and select `extensions/firefox/manifest.json`.
3. Open an article and click the **Paperclip Capture** toolbar button.

Firefox uses Manifest V3 with a background event page. Page collection runs only when
its toolbar button is clicked; the extension does not need access to all websites
at installation. A temporary add-on is removed when Firefox restarts. Permanent
installation requires a signed Firefox add-on package.

## How it works

- Extension posts captures to `POST /api/captures/` (URL + full HTML + best-effort main content + metadata).
- Server parses with a site-aware parser (PMC/OUP/Wiley/…) and falls back to generic heuristics.
- Data is stored locally:
  - SQLite: `data/db.sqlite3`
  - Artifacts: `data/artifacts/<capture_id>/`

## Artifacts

Each capture has a folder at `data/artifacts/<capture_id>/`, typically containing:

- `page.html`, `content.html`
- `article.json`, `reduced.json`
- `sections.json`, `references.json`
- `paper.md` (deterministic bundle)

## Exports

- BibTeX: `/exports/bibtex/`
- RIS: `/exports/ris/`
- Master Markdown: `/exports/master.md/`
- Chunks JSONL: `/exports/chunks.jsonl/` (retrieval-native GPT/RAG chunks)
- Papers JSONL: `/exports/papers.jsonl/`

Add `?collection=<collection_id>` to export a specific collection.

## Dev

```bash
pip install -r requirements-dev.txt
pytest
```
