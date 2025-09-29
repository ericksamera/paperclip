# services/server/captures/artifacts.py  (full replacement)
from __future__ import annotations
from typing import Any, Dict
from paperclip_parser import parse_html_to_server_parsed

def build_server_parsed(capture, extraction: Dict[str, Any] | None) -> Dict[str, Any]:
    """Return tolerant normalized structure for downstream analysis."""
    model = parse_html_to_server_parsed(capture, extraction)
    return model.model_dump()
