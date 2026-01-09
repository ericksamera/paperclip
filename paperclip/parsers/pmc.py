from __future__ import annotations

from typing import Any

from .base import ParseResult


def parse_pmc(*, url: str, dom_html: str, head_meta: dict[str, Any]) -> ParseResult:
    # Prototype stub: for now just fall back to generic via registry.
    # We'll implement real PMC selectors + reference splitting next.
    return ParseResult(
        ok=False,
        parser="pmc",
        capture_quality="suspicious",
        notes=["pmc_parser_not_implemented_yet"],
    )
