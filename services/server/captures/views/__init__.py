# services/server/captures/views/__init__.py
from __future__ import annotations

from .library import LibraryView, library_page
from .collections import (
    collection_create, collection_rename, collection_delete,
    collection_assign, collection_download_views,
)
from .captures import (
    capture_view, capture_open, capture_delete, capture_bulk_delete,
    capture_enrich_refs, capture_export, capture_artifact,
)
from .dedup import (
    dedup_review, dedup_scan_view, dedup_merge, dedup_ignore,
)
from .dashboard import (  # NEW
    collection_dashboard, collection_summary_json,
)

__all__ = [
    # library
    "LibraryView", "library_page",
    # collections
    "collection_create", "collection_rename", "collection_delete",
    "collection_assign", "collection_download_views",
    # captures
    "capture_view", "capture_open", "capture_delete", "capture_bulk_delete",
    "capture_enrich_refs", "capture_export", "capture_artifact",
    # dedup
    "dedup_review", "dedup_scan_view", "dedup_merge", "dedup_ignore",
    # dashboard
    "collection_dashboard", "collection_summary_json",
]
