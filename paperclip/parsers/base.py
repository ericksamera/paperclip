from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParseResult:
    ok: bool
    parser: str

    # Quality + confidence
    capture_quality: str = "ok"  # ok | suspicious | blocked
    blocked_reason: str = ""  # cookie_wall | paywall | bot_block | unknown
    confidence_fulltext: float = 0.0

    # Outputs (article body)
    article_html: str = ""
    article_text: str = ""

    # Outputs (references/bibliography)
    references_html: str = ""
    references_text: str = ""

    # Debug/provenance
    selected_hint: str = ""  # e.g. "article", "main", "selector:.foo", "largest_block"
    score_breakdown: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # Structured (optional; can grow later)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "parser": self.parser,
            "capture_quality": self.capture_quality,
            "blocked_reason": self.blocked_reason,
            "confidence_fulltext": self.confidence_fulltext,
            "selected_hint": self.selected_hint,
            "score_breakdown": self.score_breakdown,
            "notes": self.notes,
            "meta": self.meta,
            "article_html": self.article_html,
            "article_text": self.article_text,
            "references_html": self.references_html,
            "references_text": self.references_text,
            "stats": {
                "article_html_chars": len(self.article_html or ""),
                "article_text_chars": len(self.article_text or ""),
                "references_html_chars": len(self.references_html or ""),
                "references_text_chars": len(self.references_text or ""),
            },
        }
