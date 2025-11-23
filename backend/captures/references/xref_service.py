from __future__ import annotations

from typing import Any

from captures.models import Capture, Reference
from captures.xref import enrich_capture_via_crossref, enrich_reference_via_crossref


def enrich_capture(cap: Capture) -> dict[str, Any] | None:
    """
    Thin wrapper around captures.xref.enrich_capture_via_crossref.

    Returns a dict of updated fields (title, year, meta, etc.) or None.
    """
    return enrich_capture_via_crossref(cap)


def enrich_reference(ref: Reference) -> dict[str, Any] | None:
    """
    Thin wrapper around captures.xref.enrich_reference_via_crossref.

    Returns a dict of updated fields (title, doi, csl, etc.) or None.
    """
    return enrich_reference_via_crossref(ref)
