# services/server/captures/serializers.py
from __future__ import annotations

from rest_framework import serializers


class ReferenceInSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    raw = serializers.CharField()
    doi = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    bibtex = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    apa = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    csl = serializers.JSONField(required=False)
    # optional niceties your client sometimes includes
    title = serializers.CharField(required=False, allow_blank=True)
    issued_year = serializers.CharField(required=False, allow_blank=True)
    container_title = serializers.CharField(required=False, allow_blank=True)
    authors = serializers.ListField(child=serializers.CharField(), required=False)
    url = serializers.CharField(required=False, allow_blank=True)
    volume = serializers.CharField(required=False, allow_blank=True)
    issue = serializers.CharField(required=False, allow_blank=True)
    pages = serializers.CharField(required=False, allow_blank=True)
    publisher = serializers.CharField(required=False, allow_blank=True)
    issn = serializers.CharField(required=False, allow_blank=True)
    isbn = serializers.CharField(required=False, allow_blank=True)


class ExtractionSerializer(serializers.Serializer):
    meta = serializers.JSONField()  # {title, doi, issued_year, journal, ...}
    csl = serializers.JSONField(required=False)  # CSL-JSON for main work
    content_html = serializers.CharField(required=False, allow_blank=True)
    references = ReferenceInSerializer(many=True, required=False)
    figures = serializers.ListField(child=serializers.JSONField(), required=False)
    tables = serializers.ListField(child=serializers.JSONField(), required=False)


class CaptureInSerializer(serializers.Serializer):
    source_url = serializers.URLField()
    captured_at = serializers.DateTimeField(required=False)  # optional for now
    dom_html = serializers.CharField(required=False, allow_blank=True)
    selection_html = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    extraction = ExtractionSerializer()
    rendered = serializers.DictField(required=False)  # {markdown, filename}
    client = serializers.DictField(required=False)  # {paperclip_version, ...}
