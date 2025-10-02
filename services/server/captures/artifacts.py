# services/server/captures/artifacts.py
from __future__ import annotations

import importlib
from typing import Any, Dict

def build_server_parsed(cap, extraction: Dict[str, Any]) -> Dict[str, Any]:
    """
    Canonical adapter to the paperclip-parser package.

    The public API is: parse_html_to_server_parsed(cap, extraction) -> pydantic model or dict
    We normalize the result to a plain dict so json.dump works and downstream .get() calls are safe.
    Any exception falls back to a tiny placeholder doc to keep ingest resilient.
    """
    # Best-effort import of optional parser
    try:
        parser_mod = importlib.import_module("paperclip_parser")
        parse = getattr(parser_mod, "parse_html_to_server_parsed")
    except Exception:
        return _fallback_doc(cap, extraction)

    try:
        out = parse(cap, extraction)  # <- correct, modern signature
        # Normalize to plain dict regardless of model type
        if isinstance(out, dict):
            return out
        if hasattr(out, "model_dump"):            # pydantic v2
            return out.model_dump()               # type: ignore[attr-defined]
        if hasattr(out, "dict"):                  # pydantic v1
            return out.dict()                     # type: ignore[attr-defined]
        return _fallback_doc(cap, extraction)     # unknown type
    except Exception:
        return _fallback_doc(cap, extraction)

def _fallback_doc(cap, extraction: Dict[str, Any]) -> Dict[str, Any]:
    # Minimal doc; uses keys expected by artifact_pipeline (metadata/references/title)
    return {
        "id": str(getattr(cap, "id", "")) or "fallback",
        "title": (getattr(cap, "title", "") or (extraction or {}).get("title") or "").strip(),
        "url": getattr(cap, "url", None),
        "metadata": {},
        "references": [],
    }
