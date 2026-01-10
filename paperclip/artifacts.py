from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .constants import ALLOWED_ARTIFACTS

ALLOWED_ARTIFACTS_SET = set(ALLOWED_ARTIFACTS)


def artifact_path(artifacts_root: Path, capture_id: str, name: str) -> Path:
    """
    Returns the absolute artifact path under artifacts_root for a capture.

    NOTE: Does not validate `name` — call sites should validate against
    ALLOWED_ARTIFACTS_SET when serving files.
    """
    return artifacts_root / str(capture_id) / str(name)


def list_present_artifacts(
    *,
    artifacts_root: Path,
    capture_id: str,
    allowed_artifacts: Iterable[str] = ALLOWED_ARTIFACTS,
) -> list[str]:
    """
    Lists artifacts that exist on disk for the given capture_id, filtered to allowed_artifacts.
    """
    allowed = set(allowed_artifacts)
    cap_dir = artifacts_root / str(capture_id)
    if not cap_dir.exists() or not cap_dir.is_dir():
        return []

    out: list[str] = []
    for p in cap_dir.iterdir():
        if p.is_file() and p.name in allowed:
            out.append(p.name)

    # Stable-ish ordering for UI
    out.sort()
    return out


def read_text_artifact(
    *,
    artifacts_root: Path,
    capture_id: str,
    name: str,
    max_bytes: int = 200_000,
) -> dict[str, Any]:
    """
    Safe-ish helper for bounded previews.
    Reads a UTF-8-ish text artifact with a hard max byte size, reports truncation, never raises.
    """
    p = artifact_path(artifacts_root, capture_id, name)

    if not p.exists() or not p.is_file():
        return {
            "name": name,
            "exists": False,
            "text": "",
            "truncated": False,
            "chars": 0,
        }

    try:
        raw = p.read_bytes()
    except Exception:
        return {
            "name": name,
            "exists": True,
            "text": "",
            "truncated": False,
            "chars": 0,
        }

    truncated = False
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
        truncated = True

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = ""

    if truncated:
        text = text.rstrip() + "\n… (truncated)"

    return {
        "name": name,
        "exists": True,
        "text": text,
        "truncated": truncated,
        "chars": len(text),
    }
