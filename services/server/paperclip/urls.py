# services/server/paperclip/urls.py
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from django.urls import path, re_path
from captures import views as cap_views
from analysis import views as analysis_views
from paperclip.api import CaptureViewSet, healthz, enrich_doi
from paperclip.debug import clear_cache, wipe_all

router = DefaultRouter()
router.register(r"captures", CaptureViewSet, basename="api-captures")

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="library", permanent=False), name="root"),

    # Library UI
    path("library/", cap_views.LibraryView.as_view(), name="library"),
    path("captures/", cap_views.LibraryView.as_view(), name="captures"),
    path("library/page/", cap_views.library_page, name="library_page"),

    # Collections
    path("collections/create/", cap_views.collection_create, name="collection_create"),
    path("collections/<int:pk>/rename/", cap_views.collection_rename, name="collection_rename"),
    path("collections/<int:pk>/delete/", cap_views.collection_delete, name="collection_delete"),
    path("collections/<int:pk>/assign/", cap_views.collection_assign, name="collection_assign"),
    path("collections/<str:cid>/download-views.zip", cap_views.collection_download_views, name="collection_download_views"),

    # Dedup UI
    path("dedup/", cap_views.dedup_review, name="dedup_review"),
    path("dedup/scan/", cap_views.dedup_scan_view, name="dedup_scan"),
    path("dedup/merge/", cap_views.dedup_merge, name="dedup_merge"),
    path("dedup/ignore/", cap_views.dedup_ignore, name="dedup_ignore"),

    # Bulk + export
    path("captures/bulk-delete/", cap_views.capture_bulk_delete, name="capture_bulk_delete"),
    path("captures/export/", cap_views.capture_export, name="capture_export"),

    # Detail / actions
    path("captures/<uuid:pk>/", cap_views.capture_view, name="capture_detail"),
    path("captures/<uuid:pk>/view/", cap_views.capture_view, name="capture_view"),
    path("captures/<uuid:pk>/delete/", cap_views.capture_delete, name="capture_delete"),
    path("captures/<uuid:pk>/open/", cap_views.capture_open, name="capture_open"),
    path("captures/<uuid:pk>/enrich-refs/", cap_views.capture_enrich_refs, name="capture_enrich_refs"),

    # Artifacts
    path("captures/<uuid:pk>/artifact/<str:basename>/", cap_views.capture_artifact, name="artifact"),

    # Analysis (Graph)
    path("runs/", analysis_views.RunsListView.as_view(), name="analysis_runs"),
    path("graph/", analysis_views.LatestGraphView.as_view(), name="analysis_graph"),
    path("graph/embed/", analysis_views.GraphEmbedView.as_view(), name="analysis_graph_embed"),
    path("runs/run-now/", analysis_views.RunNowView.as_view(), name="analysis_run_now"),
    path("analysis/run/", analysis_views.RunNowView.as_view(), name="analysis_run"),
    path("runs/<int:pk>/progress.json", analysis_views.RunProgressView.as_view(), name="analysis_progress"),

    # API
    path("api/", include(router.urls)),
    path("api/healthz/", healthz, name="healthz"),
    path("api/captures/<uuid:pk>/enrich-doi/", enrich_doi, name="enrich_doi"),

    # Dev helpers
    path("debug/clear-cache/", clear_cache, name="debug_clear_cache"),
    path("debug/wipe-all/", wipe_all, name="debug_wipe_all"),

    path("admin/", admin.site.urls),
]
