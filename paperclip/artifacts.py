from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from uuid import UUID

from django.conf import settings


def get_artifact_dir(capture_id: str) -> Path:
    base = Path(getattr(settings, "ARTIFACTS_DIR", Path.cwd() / "artifacts"))
    path = base / capture_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _json_default(o: Any) -> Any:
    """
    Convert common non-JSON types to JSON-friendly values.

    Learned-from-past-mistakes rule: never blow up on datetime—always emit ISO-8601.
    """
    if isinstance(o, (datetime, date, time)):
        # Keep timezone info if present. If naive, this still round-trips as a string.
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, UUID):
        return str(o)
    if isinstance(o, set):
        return list(o)
    # For other unsupported types, fall back to the default error so we notice.
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def write_text_artifact(capture_id: str, basename: str, text: str) -> Path:
    # basename must be a simple file name, no path segments
    if "/" in basename or "\\" in basename:
        raise ValueError("Invalid artifact file name.")
    target = get_artifact_dir(capture_id) / basename
    with open(target, "w", encoding="utf-8") as f:
        f.write(text or "")
    return target


def write_json_artifact(capture_id: str, basename: str, obj: Any) -> Path:
    """
    Write JSON to disk, safely converting datetimes and a few other common types.

    This prevents crashes like:
      TypeError: Object of type datetime is not JSON serializable
    when serializing serializer data that still contains Python datetime objects.
    """
    if "/" in basename or "\\" in basename:
        raise ValueError("Invalid artifact file name.")
    target = get_artifact_dir(capture_id) / basename
    with open(target, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=_json_default)
        f.write("\n")
    return target
