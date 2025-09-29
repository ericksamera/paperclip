# services/server/paperclip/api.py
from __future__ import annotations
import json
from typing import Any, Dict

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets, serializers
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from captures.models import Capture
from captures.serializers import CaptureInSerializer
from paperclip.artifacts import open_artifact, artifact_path
from paperclip.ingest import ingest_capture  # orchestrates DB writes + artifacts

# Patch target for tests: keep symbol here and delegate at call-time
def build_server_parsed(*args, **kwargs) -> Dict[str, Any]:  # pragma: no cover
    from captures.artifacts import build_server_parsed as _sp
    return _sp(*args, **kwargs)

class _CaptureListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Capture
        fields = ("id", "title", "url")

class _CapPagination(PageNumberPagination):
    page_size_query_param = "page_size"

class CaptureViewSet(viewsets.ViewSet):
    """
    POST /api/captures/          -> ingest_capture(payload)
    GET  /api/captures/          -> paged list (id, title, url)
    GET  /api/captures/<id>/     -> capture details + normalized doc if present
    """

    def list(self, request):
        qs = Capture.objects.all().order_by("-created_at")
        paginator = _CapPagination()
        page = paginator.paginate_queryset(qs, request)
        ser = _CaptureListSerializer(page, many=True)
        return paginator.get_paginated_response(ser.data)

    def retrieve(self, request, pk=None):
        c = Capture.objects.filter(pk=pk).first()
        if not c:
            return Response({"detail": "Not found"}, status=404)

        # Try canonical "server_parsed.json" then legacy "doc.json"
        doc = None
        for name in ("server_parsed.json", "doc.json"):
            try:
                p = artifact_path(str(c.id), name)
                if p.exists():
                    with open_artifact(str(c.id), name, "rb") as fh:
                        doc = json.load(fh)
                        break
            except Exception:
                doc = None

        return Response({
            "id": str(c.id),
            "title": c.title,
            "url": c.url,
            "doi": c.doi,
            "year": c.year,
            "meta": c.meta or {},
            "csl": c.csl or {},
            "server_parsed": doc,
        })

    def create(self, request):
        ser = CaptureInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        cap, summary = ingest_capture(ser.validated_data)
        return Response({"capture_id": str(cap.id), "summary": summary}, status=status.HTTP_201_CREATED)

# Utility endpoints used by urls.py
def healthz(_request):
    return JsonResponse({"ok": True})

def enrich_doi(_request, pk):
    # kept for compatibility; main ingest already enriches automatically
    cap = get_object_or_404(Capture, pk=pk)
    return JsonResponse({"ok": True, "id": str(cap.id)})
