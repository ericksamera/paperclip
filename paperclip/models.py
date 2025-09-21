from django.db import models

class Capture(models.Model):
    id = models.CharField(primary_key=True, max_length=40)
    url = models.URLField()
    title = models.TextField(blank=True)
    captured_at = models.DateTimeField()
    dom_html = models.TextField()
    content_html = models.TextField()
    markdown = models.TextField()
    meta = models.JSONField(default=dict)
    csl = models.JSONField(default=dict)
    figures = models.JSONField(default=list)
    tables = models.JSONField(default=list)

    def __str__(self):
        return f"{self.id} — {self.title or self.url}"

class Reference(models.Model):
    capture = models.ForeignKey(Capture, on_delete=models.CASCADE, related_name="references")

    # Linking / identity
    ref_id = models.CharField(max_length=100, blank=True, null=True)

    # Lossless originals
    raw = models.TextField()
    csl = models.JSONField(default=dict)            # canonical CSL-JSON when available
    bibtex = models.TextField(blank=True, null=True)
    apa = models.TextField(blank=True, null=True)

    # Normalized core fields (for querying/exports)
    title = models.TextField(blank=True)
    authors = models.JSONField(default=list)        # [{family, given}]
    container_title = models.TextField(blank=True)  # journal / book title
    issued_year = models.CharField(max_length=9, blank=True)  # '2024' or '2024a'
    volume = models.CharField(max_length=20, blank=True)
    issue = models.CharField(max_length=20, blank=True)
    pages = models.CharField(max_length=50, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    url = models.URLField(blank=True, null=True)

    doi = models.CharField(max_length=255, blank=True, null=True)
    issn = models.CharField(max_length=32, blank=True)
    isbn = models.CharField(max_length=32, blank=True)

    def __str__(self):
        return (self.title or self.raw or "")[:100]
