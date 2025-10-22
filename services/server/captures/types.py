# services/server/captures/types.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


# ──────────────────────────────────────────────────────────────────────────────
# Reduced view (already used across the codebase)
# ──────────────────────────────────────────────────────────────────────────────
class SectionNode(TypedDict, total=False):
    """
    Structured section node used in the reduced view.
    """

    title: str  # e.g., "Introduction"
    paragraphs: List[str]  # plain text paragraphs
    children: List["SectionNode"]  # optional nested sections


class ReducedSections(TypedDict, total=False):
    """
    Content portion of the reduced view.
    """

    abstract: Optional[str]
    abstract_or_body: List[str]
    sections: List[SectionNode]


class ReducedView(TypedDict):
    """
    Canonical "reduced view" persisted for UI + analysis.
    All keys are always present (possibly empty).
    """

    title: str
    meta: Dict[str, Any]
    sections: ReducedSections
    references: List[Dict[str, Any]]


# ──────────────────────────────────────────────────────────────────────────────
# NEW: Minimal CSL types (for Crossref & author lists)
# We use a normalized, *light* view that still accepts minor variations.
# ──────────────────────────────────────────────────────────────────────────────
class CSLAuthor(TypedDict, total=False):
    family: str
    given: str
    # accept a few common alternates without caring about them at runtime
    last: str
    first: str
    literal: str
    sequence: str  # "first" / "additional"


class CSL(TypedDict, total=False):
    # NOTE: Crossref may return `title` as a string or a [str] list.
    title: str | List[str]
    author: List[CSLAuthor]
    # We keep `issued` loose because the real key is "date-parts"
    # and hyphens aren't valid TypedDict field names.
    issued: Dict[str, Any]
    # we normalize "container-title" → container_title for convenience
    container_title: str | List[str]
    DOI: str
    page: str
    volume: str
    issue: str
    abstract: str


__all__ = [
    "SectionNode",
    "ReducedSections",
    "ReducedView",
    "CSLAuthor",
    "CSL",
]
