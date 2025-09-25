from __future__ import annotations
from rest_framework import serializers


class ReferenceInSerializer(serializers.Serializer):
    # All optional/tolerant — we just persist what the client sends
    id = serializers.CharField(required=False, allow_blank=True)
    raw = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    doi = serializers.CharField(required=False, allow_blank=True)
    url = serializers.CharField(required=False, allow_blank=True)
    issued_year = serializers.CharField(required=False, allow_blank=True)
    container_title = serializers.CharField(required=False, allow_blank=True)
    authors = serializers.ListField(child=serializers.DictField(), required=False)
    csl = serializers.DictField(required=False)

    # Structured extras (safe if absent)
    volume = serializers.CharField(required=False, allow_blank=True)
    issue = serializers.CharField(required=False, allow_blank=True)
    pages = serializers.CharField(required=False, allow_blank=True)
    publisher = serializers.CharField(required=False, allow_blank=True)
    issn = serializers.CharField(required=False, allow_blank=True)
    isbn = serializers.CharField(required=False, allow_blank=True)
    bibtex = serializers.CharField(required=False, allow_blank=True)
    apa = serializers.CharField(required=False, allow_blank=True)


class ExtractionSerializer(serializers.Serializer):
    meta = serializers.DictField(required=False)
    csl = serializers.DictField(required=False)
    content_html = serializers.CharField(required=False, allow_blank=True)
    references = ReferenceInSerializer(many=True, required=False)
    figures = serializers.ListField(child=serializers.DictField(), required=False)
    tables = serializers.ListField(child=serializers.DictField(), required=False)


class CaptureInSerializer(serializers.Serializer):
    # New and old payloads are normalized in the view; keep everything optional here
    source_url = serializers.CharField(required=False, allow_blank=True)
    captured_at = serializers.DateTimeField(required=False)
    dom_html = serializers.CharField(required=False, allow_blank=True)
    selection_html = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    extraction = ExtractionSerializer(required=False)
    rendered = serializers.DictField(required=False)
    client = serializers.DictField(required=False)
