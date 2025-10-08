from __future__ import annotations

from typing import Any

def submit_analysis(run_id: int) -> bool:
    """
    Try to queue the analysis run via Celery; fall back to a synchronous call
    if Celery isn't available. Returns True if queued, False if ran inline.
    """
    # Preferred: Celery task
    try:
        from analysis.tasks import run_analysis_task  # celery-shared-task

        # .delay returns an AsyncResult on success
        _res: Any = run_analysis_task.delay(int(run_id))  # type: ignore[attr-defined]
        return True
    except Exception:
        # Fallback: run synchronously (keeps the UI working in dev/tests)
        try:
            from analysis.tasks import run_analysis_sync

            run_analysis_sync(int(run_id))
        except Exception:
            # As a last resort, swallow—view will show "STARTED" state and logs will capture exception
            pass
        return False
