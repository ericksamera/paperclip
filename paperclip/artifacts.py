from __future__ import annotations
from pathlib import Path
from typing import Any
from django.conf import settings
import json
import os

def get_artifact_dir(capture_id: str) -> Path:
    base = Path(getattr(settings, "ARTIFACTS_DIR", Path.cwd() / "artifacts"))
    path = base / capture_id
    path.mkdir(parents=True, exist_ok=True)
    return path

def write_text_artifact(capture_id: str, basename: str, text: str) -> Path:
    # basename must be a simple file name, no path segments
    if "/" in basename or "\\" in basename:
        raise ValueError("Invalid artifact file name.")
    target = get_artifact_dir(capture_id) / basename
    with open(target, "w", encoding="utf-8") as f:
        f.write(text or "")
    return target

def write_json_artifact(capture_id: str, basename: str, obj: Any) -> Path:
    if "/" in basename or "\\" in basename:
        raise ValueError("Invalid artifact file name.")
    target = get_artifact_dir(capture_id) / basename
    with open(target, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return target
