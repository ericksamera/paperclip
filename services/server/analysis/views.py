# services/server/analysis/views.py
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt

from paperclip.jobs import submit_analysis

from .models import AnalysisRun


class RunsListView(View):
    template_name = "analysis/runs.html"

    def get(self, request):
        runs = AnalysisRun.objects.all()[:200]
        return render(request, self.template_name, {"runs": runs})


class RunNowView(View):
    def post(self, request):
        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        out_dir = settings.ANALYSIS_DIR / f"run-{ts}"
        out_dir.mkdir(parents=True, exist_ok=True)
        run = AnalysisRun.objects.create(
            status="PENDING", progress=0, out_dir=str(out_dir), log=""
        )
        queued = submit_analysis(int(run.pk))
        messages.success(
            request, f"Analysis run {int(run.pk)} - {'QUEUED' if queued else 'STARTED'}"
        )
        return redirect("analysis_graph")

    def get(self, request):
        return redirect("analysis_runs")


class LatestGraphView(View):
    template_name = "analysis/graph.html"

    def get(self, request):
        run_qs = AnalysisRun.objects.all()
        runs = list(run_qs.values("id", "status", "created_at", "log")[:100])
        selected_id = request.GET.get("run")
        if selected_id and run_qs.filter(pk=selected_id).exists():
            run_id = int(selected_id)
        else:
            first = run_qs.first()
            run_id = int(first.pk) if first else None
        embed_url = (
            (reverse("analysis_graph_embed") + (f"?run={run_id}" if run_id else ""))
            if run_id
            else None
        )
        latest = run_qs.first()
        return render(
            request,
            self.template_name,
            {
                "no_run": (not run_id),
                "embed_url": embed_url,
                "runs": runs,
                "selected_id": run_id,
                "latest_id": (int(latest.pk) if latest else None),
            },
        )


@method_decorator(xframe_options_exempt, name="dispatch")
class GraphEmbedView(View):
    """Render chosen run's graph via template (reads graph.json)."""

    template_name = "analysis/embed.html"

    def get(self, request):
        run_id = request.GET.get("run")
        run = (
            AnalysisRun.objects.filter(pk=run_id).first()
            if run_id
            else AnalysisRun.objects.first()
        )
        if not run:
            return HttpResponse(
                "<html><body>No graph yet.</body></html>", content_type="text/html"
            )
        p = Path(run.out_dir) / "graph.json"
        if not p.exists():
            return HttpResponse(
                "<html><body>No graph yet.</body></html>", content_type="text/html"
            )
        data_json = p.read_text("utf-8")
        return render(request, self.template_name, {"data_json": data_json, "run": run})


class RunProgressView(View):
    def get(self, _request, pk: int):
        run = AnalysisRun.objects.filter(pk=pk).first()
        if not run:
            return JsonResponse({"ok": False, "error": "not_found"}, status=404)
        return JsonResponse(
            {
                "ok": True,
                "id": int(run.pk),
                "status": run.status,
                "progress": run.progress,
                "log": run.log,
            }
        )
