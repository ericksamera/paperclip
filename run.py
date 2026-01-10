from __future__ import annotations

from paperclip.app import create_app

app = create_app()

if __name__ == "__main__":
    # Local dev server
    app.run(host="127.0.0.1", port=8000, debug=bool(app.config.get("DEBUG")))
