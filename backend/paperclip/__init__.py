# services/server/paperclip/__init__.py
from __future__ import annotations

from typing import Any

celery_app: Any

try:
    from .celery import app as celery_app
except Exception:  # pragma: no cover
    celery_app = None
