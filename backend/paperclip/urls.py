# backend/paperclip/urls.py
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from captures import views as cap_views
from paperclip.api import CaptureViewSet, enrich_doi, healthz
from paperclip.debug import clear_cache, set_openai_key, wipe_all

router = DefaultRouter()
router.register(r"captures", CaptureViewSet, basename="api-captures")

urlpatterns = [
    # Optional QA app include (if present)
    path("", include("paperclip.qa.urls")),
    # Home → Library
    path(
        "",
        RedirectView.as_view(pattern_name="library", permanent=False),
        name="root",
    ),
    # Library UI
    path("library/", cap_views.LibraryView.as_view(), name="library"),
    path("captures/", cap_views.LibraryView.as_view(), name="captures"),
    path("library/page/", cap_views.library_page, name="library_page"),
    # Collections
    path("collections/create/", cap_views.collection_create, name="collection_create"),
    path(
        "collections/<int:pk>/rename/",
        cap_views.collection_rename,
        name="collection_rename",
    ),
    path(
        "collections/<int:pk>/delete/",
        cap_views.collection_delete,
        name="collection_delete",
    ),
    path(
        "collections/<int:pk>/assign/",
        cap_views.collection_assign,
        name="collection_assign",
    ),
    path(
        "collections/<int:pk>/download-views.zip",
        cap_views.collection_download_views,
        name="collection_download_views",
    ),
    # Collection dashboard + summary API
    path(
        "collections/<int:pk>/dashboard/",
        cap_views.collection_dashboard,
        name="collection_dashboard",
    ),
    path(
        "collections/<int:pk>/summary.json/",
        cap_views.collection_summary_json,
        name="collection_summary_json",
    ),
    # Q&A workspace
    path(
        "collections/<int:pk>/qaw/",
        cap_views.collection_qaw,
        name="collection_qaw",
    ),
    # Dedup UI
    path("dedup/", cap_views.dedup_review, name="dedup_review"),
    path("dedup/scan/", cap_views.dedup_scan_view, name="dedup_scan"),
    path("dedup/ignore/", cap_views.dedup_ignore, name="dedup_ignore"),
    path("dedup/merge/", cap_views.dedup_merge, name="dedup_merge"),
    # Bulk actions + export
    path(
        "captures/bulk-delete/",
        cap_views.capture_bulk_delete,
        name="capture_bulk_delete",
    ),
    path(
        "captures/export/",
        cap_views.capture_export,
        name="capture_export",
    ),  # CSV
    path(
        "captures/export.bib",
        cap_views.library_export_bibtex,
        name="capture_export_bibtex",
    ),  # BibTeX
    path(
        "captures/export.ris",
        cap_views.library_export_ris,
        name="capture_export_ris",
    ),  # RIS
    # Detail / actions on a single capture
    path(
        "captures/<uuid:pk>/",
        cap_views.capture_view,
        name="capture_view",
    ),
    path(
        "captures/<uuid:pk>/open/",
        cap_views.capture_open,
        name="capture_open",
    ),
    path(
        "captures/<uuid:pk>/delete/",
        cap_views.capture_delete,
        name="capture_delete",
    ),
    path(
        "captures/<uuid:pk>/artifact/<str:basename>/",
        cap_views.capture_artifact,
        name="capture_artifact",
    ),
    path(
        "captures/<uuid:pk>/enrich-doi/",
        enrich_doi,
        name="capture_enrich_doi",
    ),
    path(
        "captures/<uuid:pk>/enrich-refs/",
        cap_views.capture_enrich_refs,
        name="capture_enrich_refs",
    ),
    # Debug / health
    path("debug/clear-cache/", clear_cache, name="pc_clear_cache"),
    path("debug/wipe-all/", wipe_all, name="pc_wipe_all"),
    path("debug/openai/", set_openai_key, name="pc_set_openai"),
    path("healthz/", healthz, name="healthz"),
    # Admin + API router
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
]
