# services/server/paperclip/debug.py
from __future__ import annotations

import shutil
from contextlib import suppress
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from analysis.models import AnalysisRun
from captures.models import Capture, Reference


def _rm_tree(p: Path) -> None:
    with suppress(Exception):
        if p.exists():
            shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)


@require_POST
def clear_cache(request: HttpRequest) -> HttpResponse:
    """Delete everything under data/cache/* and recreate the folder."""
    cache_root = settings.DATA_DIR / "cache"
    _rm_tree(cache_root)
    messages.success(request, "Cache cleared.")
    return redirect("library")


@require_POST
def wipe_all(request: HttpRequest) -> HttpResponse:
    """
    DEVELOPMENT ONLY: delete DB rows + artifacts + analysis outputs.
    """
    # Delete files first (fast + safe)
    _rm_tree(settings.ARTIFACTS_DIR)
    _rm_tree(settings.ANALYSIS_DIR)
    # DB wipe in a transaction
    with transaction.atomic():
        Reference.objects.all().delete()
        Capture.objects.all().delete()
        AnalysisRun.objects.all().delete()
    messages.success(request, "All ingested data and artifacts removed.")
    return redirect("library")
