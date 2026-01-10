from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    raw = raw.strip().lower()
    if raw in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except Exception:
        return default


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def load_config(*, repo_root: Path) -> dict[str, Any]:
    """
    Load configuration from environment variables with safe defaults.

    Supported env vars:
      - DATA_DIR
      - DB_PATH
      - ARTIFACTS_DIR
      - MAX_CONTENT_LENGTH (bytes)
      - SECRET_KEY
      - DEBUG
    """
    debug = _env_bool("DEBUG", default=False)

    data_dir = _env_path("DATA_DIR") or (repo_root / "data")
    db_path = _env_path("DB_PATH") or (data_dir / "db.sqlite3")
    artifacts_dir = _env_path("ARTIFACTS_DIR") or (data_dir / "artifacts")

    # Default 25MB unless overridden
    max_content_length = _env_int("MAX_CONTENT_LENGTH", default=25 * 1024 * 1024)

    secret_key = os.environ.get("SECRET_KEY")
    if secret_key is not None:
        secret_key = secret_key.strip() or None

    # Avoid a production footgun:
    # - In DEBUG, keep a predictable dev key if none provided
    # - Otherwise generate a random ephemeral key (better than "paperclip-dev")
    if not secret_key:
        secret_key = "paperclip-dev" if debug else uuid.uuid4().hex

    return {
        "DEBUG": debug,
        "DATA_DIR": data_dir,
        "DB_PATH": db_path,
        "ARTIFACTS_DIR": artifacts_dir,
        "MAX_CONTENT_LENGTH": max_content_length,
        "SECRET_KEY": secret_key,
    }
