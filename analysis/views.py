from __future__ import annotations
import threading
from pathlib import Path
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.views.generic import TemplateView, ListView, View
from django.core.management import call_command
from .models import AnalysisRun

class RunNowView(View):
    def post(self, request):
        def worker():
            # creates an AnalysisRun row when done
            call_command("run_miner", "--auto-k", "--edge-mode", "both")
        threading.Thread(target=worker, daemon=True).start()
        messages.success(request, "Analysis started. View Runs/Graph for results.")
        return redirect("library")  # normalized target

class RunsListView(ListView):
    model = AnalysisRun
    template_name = "analysis/runs.html"
    context_object_name = "runs"

class LatestGraphView(TemplateView):
    template_name = "analysis/graph.html"
    def render_to_response(self, context, **kwargs):
        run = AnalysisRun.objects.first()
        if not run:
            return super().render_to_response({"no_run": True}, **kwargs)
        p = Path(run.out_dir) / "graph.html"
        if not p.exists():
            raise Http404()
        return FileResponse(open(p, "rb"), content_type="text/html")
