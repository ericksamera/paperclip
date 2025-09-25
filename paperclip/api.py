# paperclip/api.py
from rest_framework import viewsets, mixins, serializers, status
from rest_framework.response import Response
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
import requests

from captures.models import Capture, Reference
from captures.serializers import CaptureInSerializer  # input payload schema

# ---------- Output serializers ----------
class ReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reference
        exclude = ("capture",)

class CaptureSerializer(serializers.ModelSerializer):
    references = ReferenceSerializer(many=True, read_only=True)
    class Meta:
        model = Capture
        fields = ["id", "created_at", "url", "title", "doi", "year", "meta", "csl", "references"]

# ---------- Helpers ----------
def _s(v):
    """Coerce None/falsey to empty string for CharFields that are NOT NULL in DB."""
    return v if isinstance(v, str) else (v or "")

# ---------- ViewSet ----------
class CaptureViewSet(mixins.CreateModelMixin,
                     mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    queryset = Capture.objects.all().order_by("-created_at")
    serializer_class = CaptureSerializer

    def create(self, request, *args, **kwargs):
        """
        POST /api/captures/: ingest payload and persist models/artifacts.
        """
        in_ser = CaptureInSerializer(data=request.data)
        in_ser.is_valid(raise_exception=True)
        payload = in_ser.validated_data

        extraction = payload.get("extraction") or {}
        meta = extraction.get("meta") or {}

        # Initial create (title may be a generic document.title from the extension)
        cap = Capture.objects.create(
            url=_s(payload.get("source_url")),
            title=_s(meta.get("title")),   # may be generic; we may override below
            doi=_s(meta.get("doi")),
            year="",
            meta=meta,
            csl=extraction.get("csl") or {},
        )

        # Set year if client provided it
        if meta.get("issued_year"):
            cap.year = _s(str(meta["issued_year"]))

        # Parse head meta from captured DOM; prefer a citation/DC title even if we already have one
        from captures.head_meta import extract_head_meta
        head_info = extract_head_meta(payload.get("dom_html") or "")
        head_title = head_info.get("title")
        head_src   = head_info.get("title_source")
        if head_title and (head_src in ("citation", "dc") or not cap.title):
            cap.title = head_title
        if not cap.doi and head_info.get("doi"):
            cap.doi = head_info["doi"]
        if not cap.year and head_info.get("issued_year"):
            cap.year = _s(str(head_info["issued_year"]))
        cap.save(update_fields=["url", "title", "doi", "year", "meta", "csl"])

        # References
        refs_data = extraction.get("references") or []
        for ref in refs_data:
            def g(k, default=""):
                v = ref.get(k, default)
                return v if isinstance(v, str) else (v or default)
            Reference.objects.create(
                capture=cap,
                ref_id=g("id"),
                raw=g("raw"),
                title=g("title"),
                doi=g("doi"),
                url=g("url"),
                issued_year=g("issued_year"),
                container_title=g("container_title"),
                authors=ref.get("authors", []) or [],
                csl=ref.get("csl", {}) or {},
                volume=g("volume"),
                issue=g("issue"),
                pages=g("pages"),
                publisher=g("publisher"),
                issn=g("issn"),
                isbn=g("isbn"),
                bibtex=g("bibtex"),
                apa=g("apa"),
            )

        # Artifacts
        from paperclip.artifacts import write_text_artifact, write_json_artifact
        write_json_artifact(str(cap.id), "raw_ingest.json", in_ser.initial_data)

        dom_html = payload.get("dom_html") or ""
        content_html = extraction.get("content_html") or ""
        if dom_html:
            write_text_artifact(str(cap.id), "page.html", dom_html)
        if content_html:
            write_text_artifact(str(cap.id), "content.html", content_html)
        md_text = (payload.get("rendered") or {}).get("markdown")
        if md_text:
            write_text_artifact(str(cap.id), "content.md", md_text)

        # Proof summary
        ref_count = len(refs_data)
        fig_count = len(extraction.get("figures") or [])
        table_count = len(extraction.get("tables") or [])
        first_refs = [{"apa": (r.get("apa") or ""), "doi": (r.get("doi") or None)} for r in refs_data[:3]]

        # Optional server-side parse & meta merge
        from captures.reduced_view import build_reduced_view
        from captures.parsing_bridge import robust_parse
        from captures.artifacts import build_server_parsed

        parsed_view = build_reduced_view(content=None, meta=cap.meta, references=refs_data, title=cap.title)
        write_json_artifact(str(cap.id), "parsed.json", parsed_view)

        server_data = robust_parse(cap.url, content_html, dom_html)
        meta_updates = server_data.get("meta_updates") or {}
        if meta_updates:
            cap.meta = {**cap.meta, **meta_updates}
            # If server provided a better title (citation/dc), adopt it even if non-empty
            if meta_updates.get("title") and (
                meta_updates.get("title_source") in ("citation", "dc") or not cap.title
            ):
                cap.title = meta_updates["title"]
            if not cap.year and "issued_year" in meta_updates:
                cap.year = _s(str(meta_updates["issued_year"]))
            if not cap.doi and meta_updates.get("doi"):
                cap.doi = _s(meta_updates["doi"])
            cap.save(update_fields=["meta", "year", "doi", "title"])

        server_view = build_reduced_view(content=server_data.get("content_sections") or {},
                                         meta=cap.meta, references=refs_data, title=cap.title)
        write_json_artifact(str(cap.id), "server_output_reduced.json", server_view)
        write_json_artifact(str(cap.id), "server_parsed.json", build_server_parsed(cap, extraction))

        return Response({
            "capture_id": str(cap.id),
            "summary": {
                "title": cap.title or "",
                "url": cap.url or "",
                "reference_count": ref_count,
                "figure_count": fig_count,
                "table_count": table_count,
                "first_3_references": first_refs,
            },
        }, status=status.HTTP_201_CREATED)

# Health & DOI enrichment
def healthz(request):  # GET /api/healthz/
    return JsonResponse({"status": "ok"})

def enrich_doi(request, pk):  # GET /api/captures/<pk>/enrich-doi/
    capture = get_object_or_404(Capture, pk=pk)
    if not capture.doi:
        return JsonResponse({"detail": "No DOI available for this capture."}, status=404)
    try:
        cr_url = f"https://api.crossref.org/v1/works/{capture.doi}/transform/application/vnd.citationstyles.csl+json"
        resp = requests.get(cr_url, timeout=5)
        if resp.status_code == 200:
            csl_data = resp.json()
            capture.title = capture.title or csl_data.get("title", [""])[0]
            if not capture.year:
                y = csl_data.get("issued", {}).get("date-parts", [])
                if y and y[0]:
                    capture.year = str(y[0][0])
            capture.meta.setdefault("container_title", csl_data.get("container-title", [""])[0])
            capture.meta.setdefault("authors", csl_data.get("author", []))
            capture.csl = capture.csl or csl_data
            capture.save()
            return JsonResponse({"updated": {
                "title": capture.title, "year": capture.year,
                "journal": capture.meta.get("container_title")
            }})
    except Exception as e:
        return JsonResponse({"detail": "DOI enrichment failed", "error": str(e)}, status=500)
    return JsonResponse({"updated": {}})
