# services/server/paperclip/jobs.py
from __future__ import annotations

import os
from contextlib import suppress


def _use_celery() -> bool:
    return os.environ.get("PAPERCLIP_USE_CELERY", "0") in ("1", "true", "yes") and bool(
        os.environ.get("CELERY_BROKER_URL")
    )


def submit_analysis(run_id: int) -> bool:
    if _use_celery():
        with suppress(Exception):
            from analysis.tasks import run_analysis_task

            run_analysis_task.delay(run_id)
            return True
    from analysis.tasks import run_analysis_sync

    run_analysis_sync(run_id)
    return False


def submit_enrichment(capture_id: str) -> bool:
    """
    Queue enrichment of a capture+its references (Crossref).
    Returns True if queued; False if Celery isn't available.
    """
    if _use_celery():
        with suppress(Exception):
            from captures.tasks import enrich_refs_task

            enrich_refs_task.delay(str(capture_id))
            return True
    return False
