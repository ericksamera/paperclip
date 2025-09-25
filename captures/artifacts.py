from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
import json
from datetime import date, datetime, time
from uuid import UUID


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _json_default(o: Any) -> Any:
    """
    Convert common non-JSON types to JSON-friendly values.
    Learned-from-past-mistakes rule: never blow up on datetime—always emit ISO-8601.
    """
    if isinstance(o, (datetime, date, time)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, UUID):
        return str(o)
    if isinstance(o, set):
        return list(o)
    # For other unsupported types, fall back to the default error so we notice.
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def write_text(p: Path, s: str) -> None:
    ensure_dir(p.parent)
    p.write_text(s or "", encoding="utf-8")


def write_json(p: Path, obj: Any) -> None:
    """
    Write JSON to disk, safely converting datetimes and a few other common types.
    """
    ensure_dir(p.parent)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default) + "\n",
                 encoding="utf-8")


def build_server_parsed(capture, extraction: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Tiny, tolerant structure your downstream analysis can read if you need it.
    """
    meta = (extraction or {}).get("meta") or {}
    csl = (extraction or {}).get("csl") or {}
    content_html = (extraction or {}).get("content_html") or ""
    markdown = (extraction or {}).get("markdown") or ""

    return {
        "id": str(capture.id),
        "title": capture.title,
        "url": capture.url,
        "doi": capture.doi,
        "metadata": {
            **meta,
            "title": capture.title,
            "doi": capture.doi,
            "issued_year": capture.year,
            "url": capture.url,
            "csl": csl,
        },
        "abstract": [{"paragraphs": [csl.get("abstract")]}] if csl.get("abstract") else [],
        "body": [{"title": "Body", "paragraphs": [markdown or content_html]}] if (markdown or content_html) else [],
        "keywords": meta.get("keywords") or [],
        "references": [
            dict(
                id=r.ref_id or None,
                raw=r.raw,
                title=r.title,
                doi=r.doi,
                url=r.url,
                issued_year=r.issued_year,
                authors=r.authors,
                csl=r.csl,
                container_title=r.container_title,
            )
            for r in capture.references.all()
        ],
    }
