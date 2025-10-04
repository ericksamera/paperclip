from __future__ import annotations

from pathlib import Path

from celery import shared_task  # type: ignore[import-not-found]
from django.utils import timezone

from .models import AnalysisRun
from .run_pipeline import run as pipeline_run


def _execute(run_id: int) -> None:
    run = AnalysisRun.objects.get(pk=run_id)
    run.status = "RUNNING"
    run.progress = 5
    run.save(update_fields=["status", "progress"])
    out_dir = Path(run.out_dir)
    try:
        result = pipeline_run(out_dir, k=None)
        run.log = (
            f"mode={result.get('mode')} · k={result.get('k')} · "
            f"docs={result['stats']['docs']} · edges={result['stats']['edges']}"
        )
        run.status = "SUCCESS"
        run.progress = 100
        run.finished_at = timezone.now()
        run.save(update_fields=["log", "status", "progress", "finished_at"])
    except Exception as e:  # pragma: no cover
        run.log = f"ERROR: {e}"
        run.status = "FAILED"
        run.progress = 100
        run.finished_at = timezone.now()
        run.save(update_fields=["log", "status", "progress", "finished_at"])
        raise


@shared_task(name="analysis.run")
def run_analysis_task(run_id: int) -> None:
    _execute(run_id)


def run_analysis_sync(run_id: int) -> None:
    _execute(run_id)
