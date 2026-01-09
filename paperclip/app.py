from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask

from .db import close_db, init_db


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def create_app(config: dict[str, Any] | None = None) -> Flask:
    cfg = config or {}

    root = _repo_root()
    data_dir = Path(cfg.get("DATA_DIR") or (root / "data")).resolve()
    db_path = Path(cfg.get("DB_PATH") or (data_dir / "db.sqlite3")).resolve()
    artifacts_dir = Path(cfg.get("ARTIFACTS_DIR") or (data_dir / "artifacts")).resolve()

    _ensure_dirs(data_dir, artifacts_dir)

    fts_enabled = init_db(db_path)

    app = Flask(
        __name__,
        static_folder=str((root / "static").resolve()),
        template_folder=str((root / "templates").resolve()),
    )

    app.config.update(
        DATA_DIR=data_dir,
        DB_PATH=db_path,
        ARTIFACTS_DIR=artifacts_dir,
        FTS_ENABLED=fts_enabled,
    )

    if "MAX_CONTENT_LENGTH" in cfg:
        app.config["MAX_CONTENT_LENGTH"] = cfg["MAX_CONTENT_LENGTH"]

    app.secret_key = cfg.get("SECRET_KEY") or "paperclip-dev"
    app.teardown_appcontext(close_db)

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
