import uuid
from bs4 import BeautifulSoup
from django.conf import settings
from rest_framework import serializers, viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.http import HttpRequest
from .models import Capture, Reference
from .artifacts import write_text_artifact, write_json_artifact
from .parsers import parse_html
from .parsers.base import BaseParser
from .services.doi import enrich_from_doi, csl_to_doc_meta, normalize_doi

# ---------- Serializers ----------

class ReferenceInSerializer(serializers.Serializer):
    # legacy / client-sent fields
    id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    raw = serializers.CharField()
    doi = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    bibtex = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    apa = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    csl = serializers.JSONField(required=False)

    # structured fields (optional in input)
    title = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    authors = serializers.ListField(child=serializers.DictField(), required=False)
    container_title = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    issued_year = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    volume = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    issue = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    pages = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    publisher = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    issn = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    isbn = serializers.CharField(required=False, allow_null=True, allow_blank=True)

class ExtractionSerializer(serializers.Serializer):
    meta = serializers.JSONField()
    csl = serializers.JSONField(required=False)
    content_html = serializers.CharField()
    references = ReferenceInSerializer(many=True, required=False)
    figures = serializers.ListField(child=serializers.JSONField(), required=False)
    tables = serializers.ListField(child=serializers.JSONField(), required=False)

class CaptureInSerializer(serializers.Serializer):
    source_url = serializers.URLField()
    captured_at = serializers.DateTimeField()
    dom_html = serializers.CharField()
    selection_html = serializers.CharField(required=False, allow_null=True)
    extraction = ExtractionSerializer()
    rendered = serializers.DictField()
    client = serializers.DictField()

class CaptureOutSerializer(serializers.ModelSerializer):
    references = serializers.SerializerMethodField()
    class Meta:
        model = Capture
        fields = [
            "id","url","title","captured_at","dom_html","content_html",
            "markdown","meta","csl","figures","tables","references"
        ]
    def get_references(self, obj):
        out = []
        for r in obj.references.all():
            out.append({
                "ref_id": r.ref_id,
                "raw": r.raw,
                "doi": r.doi,
                "bibtex": r.bibtex,
                "apa": r.apa,
                "csl": r.csl,
                "title": r.title,
                "authors": r.authors,
                "container_title": r.container_title,
                "issued_year": r.issued_year,
                "volume": r.volume,
                "issue": r.issue,
                "pages": r.pages,
                "publisher": r.publisher,
                "url": r.url,
                "issn": r.issn,
                "isbn": r.isbn,
            })
        return out

# ---------- Views ----------

class CaptureViewSet(viewsets.ViewSet):
    def create(self, request: HttpRequest):
        data = CaptureInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payload = data.validated_data
        ext = payload["extraction"]

        capture_id = f"c_{uuid.uuid4().hex}"
        cap = Capture.objects.create(
            id=capture_id,
            url=payload["source_url"],
            title=(ext.get("meta") or {}).get("title", ""),
            captured_at=payload["captured_at"],
            dom_html=payload["dom_html"],
            content_html=ext.get("content_html", ""),
            markdown=payload.get("rendered", {}).get("markdown", ""),
            meta=ext.get("meta", {}) or {},
            csl=ext.get("csl", {}) or {},
            figures=ext.get("figures", []) or [],
            tables=ext.get("tables", []) or []
        )

        # Seed with client-side refs first (lossless & structured if provided)
        for r in (ext.get("references") or []):
            Reference.objects.create(
                capture=cap,
                ref_id=r.get("id"),
                raw=r.get("raw", ""),
                doi=r.get("doi"),
                bibtex=r.get("bibtex"),
                apa=r.get("apa"),
                csl=r.get("csl") or {},
                title=r.get("title") or "",
                authors=r.get("authors") or [],
                container_title=r.get("container_title") or "",
                issued_year=r.get("issued_year") or "",
                volume=r.get("volume") or "",
                issue=r.get("issue") or "",
                pages=r.get("pages") or "",
                publisher=r.get("publisher") or "",
                url=r.get("url") or None,
                issn=r.get("issn") or "",
                isbn=r.get("isbn") or "",
            )

        # ---- Early DOI from <head> (dom_html) ----
        dom_soup = BeautifulSoup(cap.dom_html or "", "html.parser")
        head_doi = BaseParser.find_doi_in_meta(dom_soup)
        if head_doi:
            cap.meta = {**(cap.meta or {}), "doi": head_doi}
            cap.save(update_fields=["meta"])

        # ---- Artifacts (pre-parse snapshot) ----
        write_text_artifact(cap.id, "page.html", cap.dom_html)
        write_json_artifact(cap.id, "raw_ingest.json", CaptureOutSerializer(cap).data)

        # ---- DOI enrichment (Crossref → OpenAlex fallback) ----
        doi = normalize_doi((cap.meta or {}).get("doi") or "")
        enrichment_blob = None
        if getattr(settings, "ENABLE_DOI_ENRICHMENT", True) and doi:
            enrichment_blob = enrich_from_doi(doi)
            if enrichment_blob and enrichment_blob.get("csl"):
                csl = enrichment_blob["csl"]
                cap.csl = csl or cap.csl
                meta_up = csl_to_doc_meta(csl)
                if meta_up.get("title"):
                    cap.title = meta_up["title"]
                cap.meta = {**(cap.meta or {}), **meta_up}
                cap.save(update_fields=["csl", "meta", "title"])
                write_json_artifact(cap.id, "enrichment.json", enrichment_blob)

        # ---- Server-side parsing (site adapters) ----
        html_for_parse = cap.content_html or cap.dom_html
        parsed = parse_html(cap.url, html_for_parse)

        # Merge any parser meta (e.g., DOI) if still missing
        if parsed.meta_updates:
            if not cap.meta.get("doi") and parsed.meta_updates.get("doi"):
                cap.meta = {**cap.meta, "doi": parsed.meta_updates["doi"]}
            else:
                cap.meta = {**cap.meta, **{k: v for k, v in parsed.meta_updates.items() if k != "doi"}}
            cap.save(update_fields=["meta"])

        # Replace references if parser found any (Python becomes source of truth)
        if parsed.references:
            cap.references.all().delete()
            Reference.objects.bulk_create([
                Reference(capture=cap, **r.to_model_kwargs()) for r in parsed.references
            ])

        # ---- Final snapshots (post-parse) ----
        final_state = CaptureOutSerializer(cap).data
        write_json_artifact(cap.id, "parsed.json", final_state)

        server_view = {
            "id": cap.id,
            "url": cap.url,
            "meta": cap.meta,
            "reference_count": cap.references.count(),
            "references": [
                {
                    "id": r.ref_id, "title": r.title, "doi": r.doi,
                    "container_title": r.container_title, "issued_year": r.issued_year
                }
                for r in cap.references.all()
            ],
            "enriched": bool(enrichment_blob),
        }
        if parsed.content_sections:
            server_view["content"] = parsed.content_sections
        write_json_artifact(cap.id, "server_parsed.json", server_view)

        base = request.build_absolute_uri("/").rstrip("/")
        artifact_urls = {
            "page_html": f"{base}/captures/{cap.id}/artifact/page.html",
            "raw_ingest": f"{base}/captures/{cap.id}/artifact/raw_ingest.json",
            "parsed_json": f"{base}/captures/{cap.id}/artifact/parsed.json",
            "server_parsed": f"{base}/captures/{cap.id}/artifact/server_parsed.json",
            "enrichment": f"{base}/captures/{cap.id}/artifact/enrichment.json",
        }

        refs_qs = cap.references.all()[:3]
        summary = {
            "title": cap.title,
            "url": cap.url,
            "reference_count": cap.references.count(),
            "figure_count": len(cap.figures or []),
            "table_count": len(cap.tables or []),
            "first_3_references": [{"apa": r.apa, "doi": r.doi} for r in refs_qs]
        }
        return Response(
            {"capture_id": capture_id, "summary": summary, "artifacts": artifact_urls},
            status=status.HTTP_201_CREATED
        )

    def retrieve(self, request, pk=None):
        from django.shortcuts import get_object_or_404
        cap = get_object_or_404(Capture, pk=pk)
        return Response(CaptureOutSerializer(cap).data)

    def list(self, request):
        qs = Capture.objects.order_by("-captured_at")
        limit = int(request.query_params.get("limit", 20))
        data = [CaptureOutSerializer(c).data for c in qs[:limit]]
        return Response({"results": data, "count": qs.count()})

# ---- Health & enrichment endpoints ----

@api_view(["GET"])
def healthz(_request):
    return Response({"status": "ok"})

@api_view(["POST"])
def enrich_doi(request, pk: str):
    from django.shortcuts import get_object_or_404
    cap = get_object_or_404(Capture, pk=pk)
    doi = normalize_doi((cap.meta or {}).get("doi") or "")
    if not doi:
        dom_soup = BeautifulSoup(cap.dom_html or "", "html.parser")
        head_doi = BaseParser.find_doi_in_meta(dom_soup)
        doi = normalize_doi(head_doi or "")
    if not doi:
        return Response({"detail": "No DOI available to enrich."}, status=400)
    blob = enrich_from_doi(doi)
    if not blob or not blob.get("csl"):
        return Response({"detail": "Enrichment failed or not found."}, status=502)

    csl = blob["csl"]
    cap.csl = csl or cap.csl
    meta_up = csl_to_doc_meta(csl)
    if meta_up.get("title"):
        cap.title = meta_up["title"]
    cap.meta = {**(cap.meta or {}), **meta_up}
    cap.save(update_fields=["csl", "meta", "title"])

    write_json_artifact(cap.id, "enrichment.json", blob)
    return Response({"ok": True, "meta": cap.meta, "csl": cap.csl})
