from __future__ import annotations
from pathlib import Path
from typing import Any
from django.conf import settings
import json

def artifact_dir(capture_id: str) -> Path:
    d = settings.ARTIFACTS_DIR / capture_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def artifact_path(capture_id: str, name: str) -> Path:
    return artifact_dir(capture_id) / name

def write_text_artifact(capture_id: str, name: str, text: str) -> None:
    p = artifact_path(capture_id, name)
    p.write_text(text, encoding="utf-8")

def write_json_artifact(capture_id: str, name: str, obj: Any) -> None:
    p = artifact_path(capture_id, name)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def open_artifact(capture_id: str, name: str, mode: str = "rb"):
    p = artifact_path(capture_id, name)
    return open(p, mode)

# NEW: small helper to DRY view.json reads across modules
def read_json_artifact(capture_id: str, name: str, default: Any | None = None) -> Any:
    p = artifact_path(capture_id, name)
    if not p.exists():
        return {} if default is None else default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default
