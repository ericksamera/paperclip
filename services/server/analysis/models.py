from __future__ import annotations
from django.db import models

class AnalysisRun(models.Model):
    STATUS = [
        ("PENDING", "PENDING"),
        ("RUNNING", "RUNNING"),
        ("SUCCESS", "SUCCESS"),
        ("FAILED", "FAILED"),
    ]
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="PENDING")
    progress = models.PositiveSmallIntegerField(default=0)
    out_dir = models.CharField(max_length=500, blank=True)
    log = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Run {self.pk} ({self.status})"
