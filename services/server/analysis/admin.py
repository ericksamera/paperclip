from django.contrib import admin
from .models import AnalysisRun

@admin.register(AnalysisRun)
class AnalysisRunAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "status", "out_dir")
    search_fields = ("out_dir", "log")
    list_filter = ("status",)
