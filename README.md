# Paperclip

A tiny research workbench that:
- **Captures** webpages (URL + full DOM + best-effort main content) via a Chrome MV3 extension.
- **Normalizes & stores** them on a Django server (artifacts on disk + DB rows).
- **Lets you browse** a Zotero-style Library with filters, collections, and references.
- **Builds a simple graph** (topics + citations) you can explore in the UI.

---

## Repo layout
- `services/server/` — Django app (API + UI).
- `services/worker/` — optional polling worker.
- `packages/paperclip-parser/` — HTML → normalized document helpers.
- `packages/paperclip-schemas/` — shared Pydantic models.
- `extensions/chrome/` — capture button (posts to the server).
- `data/` — generated artifacts, caches, and analysis runs (git-ignored).

---

## Quickstart

### 1) Run the server
```bash
cd services/server
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
````

Open:

* Library UI: `http://127.0.0.1:8000/library/`
* Graph UI: `http://127.0.0.1:8000/graph/`
* API root: `http://127.0.0.1:8000/api/`

### 2) Load the Chrome extension

1. Go to `chrome://extensions`, enable **Developer mode**.
2. **Load unpacked** → select `extensions/chrome/`.
3. Click the toolbar button on any article to capture it back to the server.

Captured files land under `data/artifacts/<uuid>/` (DOM, content, and JSON views).

---

## Tests

```bash
cd services/server
python manage.py test
```

---

## Notes

* The main ingest endpoint is `POST /api/captures/`.
* Local artifact/data folders are ignored by git; commit only code.
* License: add one when you’re ready (current repo is unlicensed by default).

````