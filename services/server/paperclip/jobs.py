from __future__ import annotations
import os

def _use_celery() -> bool:
    # only if celery is installed, broker is configured, and flag is enabled
    return os.environ.get("PAPERCLIP_USE_CELERY", "0") in ("1", "true", "yes") \
        and bool(os.environ.get("CELERY_BROKER_URL"))

def submit_analysis(run_id: int) -> bool:
    """Queue with Celery if available; otherwise run sync. Returns True if queued."""
    if _use_celery():
        try:
            from analysis.tasks import run_analysis_task
            run_analysis_task.delay(run_id)
            return True
        except Exception:
            pass
    from analysis.tasks import run_analysis_sync
    run_analysis_sync(run_id)
    return False
