# services/server/paperclip/debug.py
from __future__ import annotations
from pathlib import Path
import shutil

from django.conf import settings
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.db import transaction

from captures.models import Capture, Reference
from analysis.models import AnalysisRun


def _rm_tree(p: Path) -> None:
    try:
        if p.exists():
            shutil.rmtree(p)
    except Exception:
        pass
    p.mkdir(parents=True, exist_ok=True)


@require_POST
def clear_cache(request):
    """Delete everything under data/cache/* and recreate the folder."""
    cache_root = settings.DATA_DIR / "cache"
    _rm_tree(cache_root)
    messages.success(request, "Cache cleared.")
    return redirect("library")


@require_POST
def wipe_all(request):
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
