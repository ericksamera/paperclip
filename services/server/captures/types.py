# services/server/captures/types.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class SectionNode(TypedDict, total=False):
    """
    Structured section node used in the reduced view.
    """
    title: str                  # e.g., "Introduction"
    paragraphs: List[str]       # plain text paragraphs
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


__all__ = ["SectionNode", "ReducedSections", "ReducedView"]
