# services/server/captures/models.py
from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from paperclip.utils import norm_doi  # central DOI normalization


class Capture(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    url = models.CharField(max_length=1000, blank=True)
    site = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=500, blank=True)
    doi = models.CharField(max_length=255, blank=True)
    # NEW: normalized DOI persisted (NULL if unknown)
    doi_norm = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    year = models.CharField(max_length=12, blank=True)
    # Raw metadata + CSL blob as JSON
    meta = models.JSONField(default=dict, blank=True)
    csl = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]

    def save(self, *args, **kwargs):
        # Prefer explicit field; fall back to meta['doi']; normalize or set None.
        candidate = self.doi or (self.meta or {}).get("doi") or ""
        nd = norm_doi(candidate) or None
        # Only set if changed to avoid noisy updates
        if getattr(self, "doi_norm", None) != nd:
            self.doi_norm = nd
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title or self.url or str(self.id)


class Reference(models.Model):
    capture = models.ForeignKey(
        Capture, related_name="references", on_delete=models.CASCADE
    )
    ref_id = models.CharField(max_length=100, blank=True)
    raw = models.TextField(blank=True)
    title = models.CharField(max_length=500, blank=True)
    doi = models.CharField(max_length=255, blank=True)
    # NEW: normalized DOI persisted (NULL if unknown)
    doi_norm = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    url = models.CharField(max_length=1000, blank=True)
    issued_year = models.CharField(max_length=12, blank=True)
    container_title = models.CharField(max_length=500, blank=True)
    authors = models.JSONField(default=list, blank=True)
    csl = models.JSONField(default=dict, blank=True)
    volume = models.CharField(max_length=50, blank=True)
    issue = models.CharField(max_length=50, blank=True)
    pages = models.CharField(max_length=50, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    issn = models.CharField(max_length=50, blank=True)
    isbn = models.CharField(max_length=50, blank=True)
    bibtex = models.TextField(blank=True)
    apa = models.TextField(blank=True)

    class Meta:
        # Enforce uniqueness of a DOI within a single capture. Because doi_norm is
        # NULL when unknown, duplicates are allowed for non‑DOI refs on all DBs.
        unique_together: ClassVar[list[tuple[str, str]]] = [("capture", "doi_norm")]

    def save(self, *args, **kwargs):
        nd = norm_doi(self.doi or "") or None
        if getattr(self, "doi_norm", None) != nd:
            self.doi_norm = nd
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title or self.raw or (self.doi or "")


class Collection(models.Model):
    """Zotero-style folders (nesting optional)."""

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=200)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="children", on_delete=models.CASCADE
    )
    captures = models.ManyToManyField(Capture, related_name="collections", blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["name"]
        unique_together: ClassVar[list[tuple[str, str]]] = [("parent", "name")]

    def __str__(self) -> str:
        return self.name
