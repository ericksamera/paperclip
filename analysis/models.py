from django.db import models
class AnalysisRun(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    out_dir = models.CharField(max_length=2048)
    status = models.CharField(max_length=16, default="done")
    log = models.TextField(blank=True)
    class Meta: ordering = ["-created_at"]
