# services/server/captures/views/__init__.py
from __future__ import annotations

from .captures import (
    capture_artifact,
    capture_bulk_delete,
    capture_delete,
    capture_enrich_refs,
    capture_export,
    capture_open,
    capture_view,
)
from .collections import (
    collection_assign,
    collection_create,
    collection_delete,
    collection_download_views,
    collection_rename,
)
from .dashboard import (  # NEW
    collection_dashboard,
    collection_summary_json,
)
from .dedup import (
    dedup_ignore,
    dedup_merge,
    dedup_review,
    dedup_scan_view,
)
from .library import LibraryView, library_page

__all__ = [
    "LibraryView",
    "capture_artifact",
    "capture_bulk_delete",
    "capture_delete",
    "capture_enrich_refs",
    "capture_export",
    "capture_open",
    "capture_view",
    "collection_assign",
    "collection_create",
    "collection_dashboard",
    "collection_delete",
    "collection_download_views",
    "collection_rename",
    "collection_summary_json",
    "dedup_ignore",
    "dedup_merge",
    "dedup_review",
    "dedup_scan_view",
    "library_page",
]
