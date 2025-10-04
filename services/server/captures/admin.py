from django.contrib import admin

from .models import Capture, Collection, Reference


@admin.register(Capture)
class CaptureAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "title", "year", "doi")
    search_fields = ("title", "doi", "url")
    list_filter = ("year",)
    ordering = ("-created_at",)


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ("id", "capture", "title", "doi", "issued_year")
    search_fields = ("title", "raw", "doi")
    list_filter = ("issued_year",)


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "parent", "created_at")
    search_fields = ("name",)
    list_filter = ("parent",)
