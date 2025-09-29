from __future__ import annotations

import importlib
from typing import Any, Dict


def build_server_parsed(cap, extraction: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the 'server parsed' doc. We lazy-import the optional
    `paperclip_parser` so tests can patch this symbol without an import-time
    failure and local dev works without that extra package.
    """
    try:
        parser_mod = importlib.import_module("paperclip_parser")
        parse = getattr(parser_mod, "parse_html_to_server_parsed")
    except Exception:
        return _fallback_doc(cap, extraction)

    html = (extraction or {}).get("html") or (extraction or {}).get("content") or ""
    base_url = getattr(cap, "url", None)
    head_meta = getattr(cap, "head_meta", None) or (extraction or {}).get("head_meta")

    # Try common signatures; fall back if they don't match.
    try:
        return parse(html=html, base_url=base_url, head_meta=head_meta)  # type: ignore[misc]
    except TypeError:
        try:
            return parse(html, base_url, head_meta)  # type: ignore[misc]
        except Exception:
            return _fallback_doc(cap, extraction)


def _fallback_doc(cap, extraction: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(getattr(cap, "id", "")) or "fallback",
        "title": getattr(cap, "title", "") or (extraction or {}).get("title") or "",
        "url": getattr(cap, "url", None),
        "sections": [],
        "meta": {"parser": "fallback", "reason": "paperclip_parser not installed"},
    }
