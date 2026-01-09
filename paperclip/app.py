from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from flask import Flask, g, request

from .config import load_config
from .db import close_db, init_db


def _repo_root() -> Path:
    # repo_root/
    #   paperclip/
    #   templates/
    #   static/
    return Path(__file__).resolve().parent.parent


def _ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def create_app(config_overrides: dict[str, Any] | None = None) -> Flask:
    repo_root = _repo_root()

    # IMPORTANT: templates/ and static/ live at repo root, not inside the package.
    app = Flask(
        __name__,
        instance_relative_config=False,
        template_folder=str(repo_root / "templates"),
        static_folder=str(repo_root / "static"),
        static_url_path="/static",
    )

    # Base config from environment + safe defaults
    base_cfg = load_config(repo_root=repo_root)
    app.config.update(base_cfg)

    # Optional overrides (tests/dev)
    if config_overrides:
        app.config.update(config_overrides)

    # Normalize to Path objects where appropriate
    app.config["DATA_DIR"] = Path(app.config["DATA_DIR"])
    app.config["DB_PATH"] = Path(app.config["DB_PATH"])
    app.config["ARTIFACTS_DIR"] = Path(app.config["ARTIFACTS_DIR"])

    _ensure_dirs(app.config["DATA_DIR"], app.config["ARTIFACTS_DIR"])

    # Ensure DB exists and schema/migrations are applied
    fts_enabled = init_db(app.config["DB_PATH"])
    app.config["FTS_ENABLED"] = bool(fts_enabled)

    @app.before_request
    def _assign_request_id() -> None:
        rid = request.headers.get("X-Request-ID", "").strip()
        if not rid:
            rid = uuid.uuid4().hex[:12]
        g.request_id = rid

    @app.after_request
    def _add_request_id_header(resp):
        # API responses already set this in apiutil; for HTML it’s useful too.
        rid = getattr(g, "request_id", None)
        if isinstance(rid, str) and rid and "X-Request-ID" not in resp.headers:
            resp.headers["X-Request-ID"] = rid
        return resp

    @app.teardown_appcontext
    def _close_db(err: Any = None) -> None:
        close_db(err)

    from .routes.api import register as register_api_routes
    from .routes.captures import register as register_captures_routes
    from .routes.collections import register as register_collections_routes
    from .routes.exports import register as register_exports_routes
    from .routes.library import register as register_library_routes

    register_library_routes(app)
    register_collections_routes(app)
    register_captures_routes(app)
    register_exports_routes(app)
    register_api_routes(app)

    return app
