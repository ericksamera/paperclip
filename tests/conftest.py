from __future__ import annotations

from pathlib import Path

import pytest

from paperclip.app import create_app


@pytest.fixture()
def app(tmp_path: Path):
    data_dir = tmp_path / "data"
    app = create_app(
        {
            "DATA_DIR": data_dir,
            "DB_PATH": data_dir / "db.sqlite3",
            "ARTIFACTS_DIR": data_dir / "artifacts",
            "SECRET_KEY": "test",
            "MAX_CONTENT_LENGTH": 10 * 1024 * 1024,
        }
    )
    app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()
