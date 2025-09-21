from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from paperclip.api import CaptureViewSet, healthz, enrich_doi
from paperclip.views import artifact_download, view_capture

router = DefaultRouter()  # trailing slash routes for /api/captures/
router.register(r"captures", CaptureViewSet, basename="captures")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("captures/<str:pk>/artifact/<str:basename>", artifact_download),
    path("captures/<str:pk>/view/", view_capture),
    path("captures/<str:pk>/enrich/doi", enrich_doi),   # NEW
    path("healthz", healthz),
]
