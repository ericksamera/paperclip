# services/server/paperclip/qa/api.py
from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .engine import QAEngine


@require_POST
@csrf_protect
def ask_collection(request: HttpRequest, collection_id: int):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    question = (data.get("question") or "").strip()
    mode = (data.get("mode") or "hybrid").strip().lower()

    if not question:
        return JsonResponse({"error": "Missing 'question'."}, status=400)

    try:
        engine = QAEngine()  # uses SimpleORMAdapter by default
        result = engine.ask(collection_id=collection_id, question=question, mode=mode)
        return JsonResponse(result, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
