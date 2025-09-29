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
