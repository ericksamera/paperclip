from __future__ import annotations

from typing import Any

from .base import ParseResult


def parse_elsevier(
    *, url: str, dom_html: str, head_meta: dict[str, Any]
) -> ParseResult:
    # Prototype stub: for now just fall back to generic via registry.
    # We'll implement ScienceDirect-specific selectors + hydration edge cases next.
    return ParseResult(
        ok=False,
        parser="elsevier",
        capture_quality="suspicious",
        notes=["elsevier_parser_not_implemented_yet"],
    )
