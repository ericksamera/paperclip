# services/server/captures/reduced_view.py
from __future__ import annotations

from typing import Any

# -----------------------------------------------------------------------------
# One place to define the canonical persisted filename for the reduced view.
# We will continue to read legacy basenames for backwards compatibility.
# -----------------------------------------------------------------------------
CANONICAL_REDUCED_BASENAME: str = "server_output_reduced.json"
LEGACY_REDUCED_BASENAMES: tuple[str, ...] = ("view.json", "parsed.json")


def build_reduced_view(
    *,
    content: dict[str, Any] | None,
    meta: dict[str, Any] | None,
    references: list[dict[str, Any]] | None,
    title: str | None,
) -> dict[str, Any]:
    """Tiny, stable summary we persist as parsed.json / server_output_reduced.json."""
    return {
        "title": title or "",
        "meta": meta or {},
        "sections": content or {},
        "references": references or [],
    }


def read_reduced_view(capture_id: str) -> dict[str, Any]:
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
    # Keep legacy-first read order for now (no visible behavior change).
    read_order = (
        LEGACY_REDUCED_BASENAMES[0],
        CANONICAL_REDUCED_BASENAME,
        LEGACY_REDUCED_BASENAMES[1],
    )
    for name in read_order:
        try:
            data = read_json_artifact(str(capture_id), name, default=None)
        except Exception:
            data = None
        if isinstance(data, dict) and data:
            return data
    return {}


__all__ = [
    "CANONICAL_REDUCED_BASENAME",
    "LEGACY_REDUCED_BASENAMES",
    "build_reduced_view",
    "read_reduced_view",
]
