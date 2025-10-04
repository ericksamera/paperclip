from __future__ import annotations

import os

from celery import Celery

# Load .env before settings
try:
    from .env import load_env as _pc_load_env

    _pc_load_env()
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "paperclip.settings")
app = Celery("paperclip")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
