from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from paperclip.api import CaptureViewSet, healthz
from paperclip.views import artifact_download, view_capture

router = DefaultRouter()
router.register(r"captures", CaptureViewSet, basename="captures")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("captures/<str:pk>/artifact/<str:basename>", artifact_download),  # page.html / parsed.json
    path("captures/<str:pk>/view/", view_capture),  # optional HTML preview (dev)
    path("healthz", healthz),
]
