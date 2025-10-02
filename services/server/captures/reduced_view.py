# services/server/captures/reduced_view.py
from __future__ import annotations
from typing import Any, Dict, List

def build_reduced_view(*, content: Dict[str, Any] | None, meta: Dict[str, Any] | None,
                       references: List[Dict[str, Any]] | None, title: str | None) -> Dict[str, Any]:
    """Tiny, stable summary we persist as parsed.json / server_output_reduced.json"""
    return {
        "title": title or "",
        "meta": meta or {},
        "sections": content or {},
        "references": references or [],
    }

def read_reduced_view(capture_id: str) -> Dict[str, Any]:
    """
    Read the reduced projection, tolerant to historical filenames.

    Accepts any of:
      • view.json                     (legacy UI projection)
      • server_output_reduced.json    (current canonical reduced projection)
      • parsed.json                   (legacy alias for reduced)

    Always returns a dict (possibly empty).
    """
    try:
        from paperclip.artifacts import read_json_artifact
    except Exception:
        # Very defensive; if import fails, behave as empty.
        return {}

    for name in ("view.json", "server_output_reduced.json", "parsed.json"):
        try:
            data = read_json_artifact(str(capture_id), name, default=None)
        except Exception:
            data = None
        if isinstance(data, dict) and data:
            return data
    return {}

__all__ = ["build_reduced_view", "read_reduced_view"]
