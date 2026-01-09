# Paperclip

A tiny local reference manager that:

- Captures webpages via a Chrome MV3 extension (URL + full DOM HTML + best-effort main content HTML + head meta)
- Ingests via `POST /api/captures/`
- Stores artifacts on disk + normalized/reduced JSON + key fields in SQLite
- Provides a lightweight UI: Library, Capture detail, Collections, Export (BibTeX/RIS), Simple search

## Quickstart (server)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open:

- Library: [http://127.0.0.1:8000/library/](http://127.0.0.1:8000/library/)
- Collections: [http://127.0.0.1:8000/collections/](http://127.0.0.1:8000/collections/)

Data files are created locally:

- SQLite DB: `data/db.sqlite3`
- Artifacts: `data/artifacts/<capture_id>/`

## Load the Chrome extension

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select `extensions/chrome/`

By default the extension posts to:

- `http://127.0.0.1:8000/api/captures/`

If you run the server elsewhere, edit:

- `extensions/chrome/background.js` (`API_ENDPOINT`)

## Export

- Export all as BibTeX: `http://127.0.0.1:8000/exports/bibtex/`
- Export all as RIS: `http://127.0.0.1:8000/exports/ris/`
- Export a collection (preferred): add `?collection=<collection_id>`
- Back-compat: `?col=<collection_id>` also works

## Dev / tests (optional)

```bash
pip install -r requirements-dev.txt
pytest
```
