# Paperclip — Golden Path (manual, 2–3 min)

## 1) Start the server
```bash
cd services/server
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
````

Open:

* Library UI: [http://127.0.0.1:8000/library/](http://127.0.0.1:8000/library/)
* Capture detail (open any item from Library)
* Graph: [http://127.0.0.1:8000/graph/](http://127.0.0.1:8000/graph/)

## 2) Capture something (Chrome)

1. Load the unpacked extension at `extensions/chrome/`.
2. Visit any article page; click the extension button to capture.

## 3) Library sanity

* New row appears near top.
* Click row → it highlights and the details panel fills (title/venue/year, abstract/keywords when present).
* `j`/`k` keys move selection up/down.

## 4) Enrich sanity

* From detail page, trigger enrich (if present) and confirm metadata/refs populate after a moment.

## 5) Analysis sanity

* Go to **/graph**, click **Run analysis**, wait for completion indicator to clear.
* Graph renders nodes/edges (or an empty state if the library is tiny).

If any step fails, stop and triage before merging changes.
