from __future__ import annotations

from typing import Any

from .bundle import PaperBundle
from .text_standardize import standardize_text

# Section kinds we exclude from papers.jsonl (noise for “read the paper” use cases)
PAPERS_EXCLUDE_KINDS = {
    "acknowledgements",
    "author_contributions",
    "funding",
    "conflicts",
    "keywords",
}


def filtered_sections_for_papers_jsonl(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in sections:
        if not isinstance(s, dict):
            continue

        kind = str(s.get("kind") or "").strip()
        if kind in PAPERS_EXCLUDE_KINDS:
            continue

        text = standardize_text(str(s.get("text") or "")).strip()
        if not text:
            continue

        out.append(
            {
                "id": str(s.get("id") or ""),
                "kind": kind,
                "title": str(s.get("title") or ""),
                "text": text,
            }
        )
    return out


def papers_jsonl_record(bundle: PaperBundle) -> dict[str, Any]:
    """
    Canonical line shape for /exports/papers.jsonl/.

    Keep this stable; future schema changes should happen HERE.
    """
    return {
        # Identity
        "id": bundle.capture_id,
        # Provenance/time (super useful in GPT uploads)
        "captured_at": bundle.captured_at(),
        "published_date_raw": bundle.published_date_raw(),
        # Core bibliographic-ish fields
        "title": bundle.title(),
        "doi": bundle.doi(),
        "url": bundle.url(),
        "year": bundle.year(),
        "container_title": bundle.container_title(),
        "authors": bundle.authors(),
        # Parse provenance (small + stable)
        "parse_parser": bundle.parse_parser(),
        "parse_ok": bundle.parse_ok(),
        "capture_quality": bundle.capture_quality(),
        "blocked_reason": bundle.blocked_reason(),
        "confidence_fulltext": bundle.confidence_fulltext(),
        "used_for_index": bundle.used_for_index(),
        # Content
        "sections": filtered_sections_for_papers_jsonl(bundle.sections),
    }
