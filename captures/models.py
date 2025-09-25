from __future__ import annotations
import uuid
from pathlib import Path
from django.db import models
from django.conf import settings

class Capture(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    url = models.URLField(max_length=2048, blank=True)
    title = models.CharField(max_length=1024, blank=True)
    doi = models.CharField(max_length=256, blank=True)
    year = models.CharField(max_length=8, blank=True)

    meta = models.JSONField(default=dict, blank=True)
    csl  = models.JSONField(default=dict, blank=True)

    def artifact_dir(self) -> Path:
        return Path(settings.ARTIFACTS_DIR) / f"{self.id}"
    def artifact_path(self, name: str) -> Path:
        return self.artifact_dir() / name

class Reference(models.Model):
    capture = models.ForeignKey(Capture, related_name="references", on_delete=models.CASCADE)
    ref_id = models.CharField(max_length=100, blank=True)
    raw = models.TextField(blank=True)
    title = models.TextField(blank=True)
    doi = models.CharField(max_length=255, blank=True)
    url = models.URLField(max_length=2048, blank=True)
    issued_year = models.CharField(max_length=8, blank=True)
    container_title = models.CharField(max_length=512, blank=True)
    authors = models.JSONField(default=list, blank=True)
    csl = models.JSONField(default=dict, blank=True)

    volume = models.CharField(max_length=20, blank=True)
    issue = models.CharField(max_length=20, blank=True)
    pages = models.CharField(max_length=50, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    issn = models.CharField(max_length=32, blank=True)
    isbn = models.CharField(max_length=32, blank=True)
    bibtex = models.TextField(blank=True)
    apa = models.TextField(blank=True)
