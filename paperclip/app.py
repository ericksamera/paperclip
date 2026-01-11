from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from flask import Flask, g, request

from .config import load_config
from .db import close_db, init_db
from .errors import register_error_handlers
from .util import ensure_dirs


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    repo_root = _repo_root()

    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(repo_root / "templates"),
        static_folder=str(repo_root / "static"),
    )

    app.config.from_mapping(load_config(repo_root=repo_root))
    if test_config:
        app.config.update(test_config)

    # Back-compat: allow ARTIFACTS_ROOT but standardize on ARTIFACTS_DIR.
    if "ARTIFACTS_DIR" not in app.config and "ARTIFACTS_ROOT" in app.config:
        app.config["ARTIFACTS_DIR"] = app.config["ARTIFACTS_ROOT"]

    ensure_dirs(
        Path(app.config["DB_PATH"]).parent,
        Path(app.config["ARTIFACTS_DIR"]),
    )

    # Initialize DB + detect FTS once
    with app.app_context():
        db_path = Path(app.config["DB_PATH"])
        try:
            fts_enabled = init_db(db_path)
        except TypeError:
            # Extremely defensive: if init_db signature changes unexpectedly
            init_db(db_path)  # type: ignore[arg-type]
            fts_enabled = False
        app.config["FTS_ENABLED"] = bool(fts_enabled)

    register_error_handlers(app)

    @app.before_request
    def _request_id() -> None:
        rid = request.headers.get("X-Request-ID")
        g.request_id = (
            rid.strip()
            if isinstance(rid, str) and rid.strip()
            else uuid.uuid4().hex[:12]
        )

    @app.after_request
    def _request_id_header(resp):
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
