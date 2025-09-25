# paperclip/urls.py
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from captures import views as cap_views
from analysis import views as analysis_views
from paperclip.api import CaptureViewSet, healthz, enrich_doi

router = DefaultRouter()
router.register(r"captures", CaptureViewSet, basename="api-captures")

urlpatterns = [
    # Root → Library
    path("", RedirectView.as_view(pattern_name="library", permanent=False), name="root"),

    # Library / Captures (UI)
    path("library/", cap_views.LibraryView.as_view(), name="library"),
    path("captures/", cap_views.LibraryView.as_view(), name="captures"),  # alias for back-links

    # Detail / actions
    path("captures/<uuid:pk>/", cap_views.capture_view, name="capture_detail"),  # alias expected by templates
    path("captures/<uuid:pk>/view/", cap_views.capture_view, name="capture_view"),
    path("captures/<uuid:pk>/delete/", cap_views.capture_delete, name="capture_delete"),

    # Artifacts (both names map to the SAME parameter "basename")
    path("captures/<uuid:pk>/artifact/<str:basename>/", cap_views.capture_artifact, name="capture_artifact"),
    path("captures/<uuid:pk>/artifact/<str:basename>/", cap_views.capture_artifact, name="artifact"),

    # Analysis pages
    path("runs/", analysis_views.RunsListView.as_view(), name="analysis_runs"),
    path("graph/", analysis_views.LatestGraphView.as_view(), name="analysis_graph"),
    path("runs/run-now/", analysis_views.RunNowView.as_view(), name="analysis_run_now"),
    # Compatibility with older template that posts to 'analysis_run'
    path("analysis/run/", analysis_views.RunNowView.as_view(), name="analysis_run"),

    # API
    path("api/", include(router.urls)),
    path("api/healthz/", healthz, name="healthz"),
    path("api/captures/<uuid:pk>/enrich-doi/", enrich_doi, name="enrich_doi"),

    # Admin
    path("admin/", admin.site.urls),
]
