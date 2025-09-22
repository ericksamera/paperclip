import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import (
    Any,
    Callable,
    Iterable,
    Mapping,
    NamedTuple,
    Sequence,
    TypedDict,
    cast,
)

from bs4 import BeautifulSoup
from django.conf import settings
from rest_framework import serializers, viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.http import HttpRequest
from .models import Capture, Reference
from .artifacts import write_text_artifact, write_json_artifact
from .parsers import parse_with_fallback
from .parsers.base import BaseParser, ParseResult, ReferenceObj
from .services.doi import (
    EnrichmentPayload,
    csl_to_doc_meta,
    enrich_from_doi,
    normalize_doi,
)


def _reference_to_server_view(ref: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a copy of a reference payload with a backward-compatible alias."""

    ref_copy: dict[str, Any] = dict(ref or {})
    if "id" not in ref_copy:
        ref_copy["id"] = ref_copy.get("ref_id")
    return ref_copy


def _reference_needs_enrichment(ref: ReferenceObj) -> bool:
    return any(
        (
            not ref.title,
            not ref.authors,
            not ref.container_title,
            not ref.issued_year,
            not ref.volume,
            not ref.issue,
            not ref.pages,
            not ref.publisher,
            not ref.url,
        )
    )


def _enrich_reference_objs_with_doi(
    references: Iterable[ReferenceObj],
    fetcher: Callable[[str], EnrichmentPayload | None] = enrich_from_doi,
) -> None:
    """Populate missing structured fields for references that expose a DOI."""

    if not getattr(settings, "ENABLE_REFERENCE_DOI_ENRICHMENT", True):
        return

    doi_to_refs: dict[str, list[ReferenceObj]] = {}
    doi_order: list[str] = []

    for ref in references:
        doi_norm = normalize_doi(ref.doi or "")
        if not doi_norm or not _reference_needs_enrichment(ref):
            continue

        if doi_norm not in doi_to_refs:
            doi_to_refs[doi_norm] = []
            doi_order.append(doi_norm)

        doi_to_refs[doi_norm].append(ref)

    if not doi_to_refs:
        return

    cache: dict[str, EnrichmentPayload | None] = {}

    def _fetch_and_store(doi: str) -> None:
        cache[doi] = fetcher(doi)

    workers_setting = getattr(settings, "REFERENCE_DOI_ENRICHMENT_MAX_WORKERS", 4) or 1
    try:
        max_workers_config = int(workers_setting)
    except (TypeError, ValueError):
        max_workers_config = 1
    max_workers = max(1, min(len(doi_order), max_workers_config))

    if max_workers == 1:
        for doi in doi_order:
            _fetch_and_store(doi)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_and_store, doi): doi for doi in doi_order}
            for future in as_completed(futures):
                # Ensure exceptions propagate during fetch for visibility
                future.result()

    for doi in doi_order:
        blob = cache.get(doi)
        if not blob:
            continue

        csl = blob["csl"]
        if not csl:
            continue

        for ref in doi_to_refs.get(doi, []):
            ref.merge_csl(csl)


class DoiEnrichmentResult(NamedTuple):
    blob: EnrichmentPayload | None
    doi: str | None


def apply_doi_enrichment(
    capture: Capture,
    *,
    allow_head_lookup: bool = False,
) -> DoiEnrichmentResult:
    doi = normalize_doi((capture.meta or {}).get("doi") or "")
    if not doi and allow_head_lookup:
        dom_soup = BeautifulSoup(capture.dom_html or "", "html.parser")
        head_doi = BaseParser.find_doi_in_meta(dom_soup)
        doi = normalize_doi(head_doi or "")

    if not doi:
        return DoiEnrichmentResult(blob=None, doi=None)

    blob = enrich_from_doi(doi)
    if not blob:
        return DoiEnrichmentResult(blob=None, doi=doi)

    csl = blob.get("csl")
    if not csl:
        return DoiEnrichmentResult(blob=None, doi=doi)

    capture.csl = csl or capture.csl
    meta_updates = csl_to_doc_meta(csl)
    if meta_updates.get("title"):
        capture.title = meta_updates["title"]
    capture.meta = {**(capture.meta or {}), **meta_updates}
    capture.save(update_fields=["csl", "meta", "title"])
    write_json_artifact(capture.id, "enrichment.json", blob)

    return DoiEnrichmentResult(blob=cast(EnrichmentPayload, blob), doi=doi)


JsonMapping = Mapping[str, Any]


class MarkdownSection(TypedDict, total=False):
    """Representation of a parsed section suitable for markdown rendering."""

    title: str
    paragraphs: list[str]
    children: list["MarkdownSection"]


class MarkdownCaptureView(TypedDict, total=False):
    """Structure returned by :func:`_build_markdown_capture_view`."""

    metadata: dict[str, Any]
    abstract: list[MarkdownSection]
    body: list[MarkdownSection]
    keywords: list[str]
    references: list[dict[str, Any]]
    markdown: str


def _content_sections_to_markdown_paragraphs(
    content: JsonMapping | None,
) -> MarkdownCaptureView:
    """Normalise parser content into markdown-friendly structures.

    The parser output contains nested structures with optional ``markdown`` and
    ``paragraphs`` fields.  Consumers that want to work with markdown paragraphs
    benefit from a simplified structure where each section declares explicit
    paragraph lists.  This helper performs that normalisation and returns the
    pieces that can later be rendered into plain markdown text.
    """

    if not isinstance(content, Mapping):
        return {}

    def _split_markdown_chunks(markdown: str) -> list[str]:
        if not markdown.strip():
            return []

        chunks: list[str] = []
        buffer: list[str] = []
        for line in markdown.splitlines():
            if not line.strip():
                if buffer:
                    chunk = "\n".join(buffer).strip()
                    if chunk:
                        chunks.append(chunk)
                    buffer = []
                continue
            buffer.append(line.rstrip())

        if buffer:
            chunk = "\n".join(buffer).strip()
            if chunk:
                chunks.append(chunk)

        return chunks

    def _extract_paragraphs(raw: Any) -> list[str]:
        paragraphs: list[str] = []
        if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
            for entry in raw:
                if isinstance(entry, Mapping):
                    text = entry.get("markdown")
                    if isinstance(text, str):
                        stripped = text.strip()
                        if stripped:
                            paragraphs.append(stripped)
                elif isinstance(entry, str):
                    stripped = entry.strip()
                    if stripped:
                        paragraphs.append(stripped)
        return paragraphs

    def _simplify_body_section(section: JsonMapping) -> MarkdownSection:
        simplified: MarkdownSection = {}

        title = section.get("title")
        if isinstance(title, str) and title.strip():
            simplified["title"] = title.strip()

        paragraphs = _extract_paragraphs(section.get("paragraphs"))
        if not paragraphs:
            markdown = section.get("markdown")
            if isinstance(markdown, str):
                paragraphs = _split_markdown_chunks(markdown)

        if paragraphs:
            simplified["paragraphs"] = paragraphs

        children_raw = section.get("children")
        if isinstance(children_raw, Iterable) and not isinstance(children_raw, (str, bytes)):
            children: list[MarkdownSection] = []
            for child in children_raw:
                if isinstance(child, Mapping):
                    simplified_child = _simplify_body_section(child)
                    if simplified_child:
                        children.append(simplified_child)
            if children:
                simplified["children"] = children

        return simplified

    simplified_content: MarkdownCaptureView = {}

    abstract_sections = content.get("abstract")
    if isinstance(abstract_sections, Iterable) and not isinstance(abstract_sections, (str, bytes)):
        abstract_list: list[MarkdownSection] = []
        for entry in abstract_sections:
            if not isinstance(entry, Mapping):
                continue
            simplified_entry: MarkdownSection = {}
            title = entry.get("title")
            if isinstance(title, str) and title.strip():
                simplified_entry["title"] = title.strip()
            body = entry.get("body")
            paragraphs: list[str] = []
            if isinstance(body, str):
                lines = [line.strip() for line in body.splitlines() if line.strip()]
                if lines:
                    paragraphs = lines
                else:
                    stripped = body.strip()
                    if stripped:
                        paragraphs = [stripped]
            if paragraphs:
                simplified_entry["paragraphs"] = paragraphs
            if simplified_entry:
                abstract_list.append(simplified_entry)
        if abstract_list:
            simplified_content["abstract"] = abstract_list

    body_sections = content.get("body")
    if isinstance(body_sections, Iterable) and not isinstance(body_sections, (str, bytes)):
        body_list: list[MarkdownSection] = []
        for section in body_sections:
            if not isinstance(section, Mapping):
                continue
            simplified_section = _simplify_body_section(section)
            if simplified_section:
                body_list.append(simplified_section)
        if body_list:
            simplified_content["body"] = body_list

    keywords = content.get("keywords")
    if isinstance(keywords, Iterable) and not isinstance(keywords, (str, bytes)):
        keyword_values = [str(value).strip() for value in keywords if str(value).strip()]
        if keyword_values:
            simplified_content["keywords"] = keyword_values

    return simplified_content


def _build_markdown_capture_view(
    *,
    content: JsonMapping | None,
    meta: JsonMapping | None,
    references: Sequence[JsonMapping] | None,
    title: str | None = None,
) -> MarkdownCaptureView:
    """Assemble a markdown-friendly representation of the capture data.

    The resulting dictionary is lightweight but still expressive enough for
    client consumption:

    ``metadata``
        Arbitrary metadata values preserved as key/value pairs.  The capture
        title is injected when available so the markdown view always exposes a
        top-level heading.
    ``abstract`` and ``body``
        Lists of :class:`MarkdownSection` entries with paragraphs suitable for
        direct rendering.
    ``references``
        Normalised reference payloads that mirror the data returned by the API
        serializer.
    ``markdown``
        A fully-rendered markdown string that concatenates the above sections.
    """

    view: MarkdownCaptureView = {}

    metadata: dict[str, Any] = {}
    if isinstance(meta, Mapping):
        metadata.update(meta)
    if title and not metadata.get("title"):
        metadata["title"] = title
    view["metadata"] = metadata

    simplified_sections = _content_sections_to_markdown_paragraphs(content)
    for key, value in simplified_sections.items():
        if value:
            view[key] = value

    normalized_refs: list[dict[str, Any]] = []
    for ref in references or []:
        if isinstance(ref, Mapping):
            data = dict(ref)
            if data:
                normalized_refs.append(data)

    def _append_section_markdown(
        sections: Sequence[MarkdownSection] | None,
        *,
        level: int,
        lines: list[str],
    ) -> None:
        if not sections:
            return

        for section in sections:
            if not isinstance(section, Mapping):
                continue
            title_text = section.get("title")
            heading_level = max(1, min(level, 6))
            if isinstance(title_text, str) and title_text.strip():
                lines.append(f"{'#' * heading_level} {title_text.strip()}")
                lines.append("")

            paragraphs = section.get("paragraphs")
            if isinstance(paragraphs, Sequence) and not isinstance(paragraphs, (str, bytes)):
                for paragraph in paragraphs:
                    if isinstance(paragraph, str) and paragraph.strip():
                        lines.append(paragraph.strip())
                        lines.append("")

            children = section.get("children")
            if isinstance(children, Sequence) and not isinstance(children, (str, bytes)):
                _append_section_markdown(children, level=heading_level + 1, lines=lines)

    markdown_lines: list[str] = []

    if metadata:
        markdown_lines.append("## Metadata")
        markdown_lines.append("")
        for key in sorted(metadata):
            value = metadata[key]
            if value is None:
                continue
            rendered = str(value).strip()
            if rendered:
                pretty_key = key.replace("_", " ").strip()
                markdown_lines.append(f"- **{pretty_key}**: {rendered}")
        markdown_lines.append("")

    abstract_sections = simplified_sections.get("abstract")
    if isinstance(abstract_sections, Sequence) and abstract_sections:
        markdown_lines.append("## Abstract")
        markdown_lines.append("")
        _append_section_markdown(
            cast(Sequence[Mapping[str, Any]] | None, abstract_sections),
            level=3,
            lines=markdown_lines,
        )

    body_sections = simplified_sections.get("body")
    if isinstance(body_sections, Sequence) and body_sections:
        markdown_lines.append("## Body")
        markdown_lines.append("")
        _append_section_markdown(
            cast(Sequence[Mapping[str, Any]] | None, body_sections),
            level=3,
            lines=markdown_lines,
        )

    keywords = simplified_sections.get("keywords")
    if isinstance(keywords, Sequence) and keywords:
        markdown_lines.append("## Keywords")
        markdown_lines.append("")
        keyword_items = [str(word).strip() for word in keywords if str(word).strip()]
        if keyword_items:
            markdown_lines.append(", ".join(keyword_items))
            markdown_lines.append("")

    view["markdown"] = "\n".join(line for line in markdown_lines if line is not None).strip()

    view["references"] = normalized_refs

    if normalized_refs:
        ref_lines: list[str] = []
        ref_lines.append("## References")
        ref_lines.append("")
        for idx, ref in enumerate(normalized_refs, start=1):
            raw = str(ref.get("raw", "")).strip()
            if raw:
                ref_lines.append(f"{idx}. {raw}")
            else:
                ref_lines.append(f"{idx}. (reference details unavailable)")
        markdown_fragment = "\n".join(ref_lines)
        if view["markdown"]:
            view["markdown"] = f"{view['markdown'].rstrip()}\n\n{markdown_fragment}"
        else:
            view["markdown"] = markdown_fragment

    if view["markdown"]:
        view["markdown"] = view["markdown"].rstrip() + "\n"

    return view


class ReferencePayload(TypedDict, total=False):
    id: str | None
    raw: str
    doi: str | None
    bibtex: str | None
    apa: str | None
    csl: dict[str, Any]
    title: str | None
    authors: list[dict[str, str]]
    container_title: str | None
    issued_year: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    publisher: str | None
    url: str | None
    issn: str | None
    isbn: str | None


class ExtractionPayload(TypedDict, total=False):
    meta: dict[str, Any]
    csl: dict[str, Any]
    content_html: str
    references: list[ReferencePayload]
    figures: list[dict[str, Any]]
    tables: list[dict[str, Any]]


class RenderedPayload(TypedDict, total=False):
    markdown: str


class _CapturePayloadRequired(TypedDict):
    source_url: str
    captured_at: datetime
    dom_html: str
    extraction: ExtractionPayload
    rendered: RenderedPayload
    client: dict[str, Any]


class CapturePayload(_CapturePayloadRequired, total=False):
    selection_html: str | None

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
    def get_references(self, obj: Capture) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
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
    def _create_capture_record(self, capture_id: str, payload: CapturePayload) -> Capture:
        extraction = payload["extraction"]
        rendered = payload.get("rendered", {})

        markdown = rendered.get("markdown") if isinstance(rendered, dict) else ""

        raw_meta = extraction.get("meta")
        meta = raw_meta if isinstance(raw_meta, dict) else {}

        raw_csl = extraction.get("csl")
        csl = raw_csl if isinstance(raw_csl, dict) else {}

        figures = extraction.get("figures")
        if not isinstance(figures, list):
            figures = []

        tables = extraction.get("tables")
        if not isinstance(tables, list):
            tables = []

        content_html = extraction.get("content_html")
        if not isinstance(content_html, str):
            content_html = ""

        return Capture.objects.create(
            id=capture_id,
            url=payload["source_url"],
            title=meta.get("title", ""),
            captured_at=payload["captured_at"],
            dom_html=payload["dom_html"],
            content_html=content_html,
            markdown=markdown or "",
            meta=meta,
            csl=csl,
            figures=figures,
            tables=tables,
        )

    def _seed_client_references(
        self,
        capture: Capture,
        references: Iterable[ReferencePayload] | None,
    ) -> None:
        payloads = list(references or [])
        if not payloads:
            return

        objects = []
        for ref_payload in payloads:
            objects.append(
                Reference(
                    capture=capture,
                    ref_id=ref_payload.get("id"),
                    raw=ref_payload.get("raw", ""),
                    doi=ref_payload.get("doi"),
                    bibtex=ref_payload.get("bibtex"),
                    apa=ref_payload.get("apa"),
                    csl=ref_payload.get("csl") or {},
                    title=ref_payload.get("title") or "",
                    authors=ref_payload.get("authors") or [],
                    container_title=ref_payload.get("container_title") or "",
                    issued_year=ref_payload.get("issued_year") or "",
                    volume=ref_payload.get("volume") or "",
                    issue=ref_payload.get("issue") or "",
                    pages=ref_payload.get("pages") or "",
                    publisher=ref_payload.get("publisher") or "",
                    url=ref_payload.get("url") or None,
                    issn=ref_payload.get("issn") or "",
                    isbn=ref_payload.get("isbn") or "",
                )
            )

        Reference.objects.bulk_create(objects)

    def _apply_head_doi(self, capture: Capture) -> None:
        dom_soup = BeautifulSoup(capture.dom_html or "", "html.parser")
        head_doi = BaseParser.find_doi_in_meta(dom_soup)
        if not head_doi:
            return

        normalized = normalize_doi(head_doi)
        if not normalized:
            return

        capture.meta = {**(capture.meta or {}), "doi": normalized}
        capture.save(update_fields=["meta"])

    def _write_initial_artifacts(self, capture: Capture) -> None:
        write_text_artifact(capture.id, "page.html", capture.dom_html)
        write_json_artifact(capture.id, "raw_ingest.json", CaptureOutSerializer(capture).data)

    def _apply_doi_enrichment(self, capture: Capture) -> EnrichmentPayload | None:
        if not getattr(settings, "ENABLE_DOI_ENRICHMENT", True):
            return None

        result = apply_doi_enrichment(capture)
        return result.blob

    def _reconcile_parser_results(self, capture: Capture, parsed: ParseResult) -> dict[str, Any] | None:
        if parsed.meta_updates:
            current_meta = capture.meta or {}
            if not current_meta.get("doi") and parsed.meta_updates.get("doi"):
                merged_meta = {**current_meta, "doi": parsed.meta_updates["doi"]}
            else:
                merged_meta = {
                    **current_meta,
                    **{k: v for k, v in parsed.meta_updates.items() if k != "doi"},
                }
            capture.meta = merged_meta
            capture.save(update_fields=["meta"])

        if parsed.references:
            _enrich_reference_objs_with_doi(parsed.references)
            capture.references.all().delete()
            Reference.objects.bulk_create(
                [Reference(capture=capture, **ref.to_model_kwargs()) for ref in parsed.references]
            )

        return parsed.content_sections or None

    def _build_artifact_urls(
        self,
        request: HttpRequest,
        capture_id: str,
        enriched: bool,
        has_markdown_view: bool,
    ) -> dict[str, str]:
        base = request.build_absolute_uri("/").rstrip("/")
        urls = {
            "page_html": f"{base}/captures/{capture_id}/artifact/page.html",
            "raw_ingest": f"{base}/captures/{capture_id}/artifact/raw_ingest.json",
            "parsed_json": f"{base}/captures/{capture_id}/artifact/parsed.json",
            "server_parsed": f"{base}/captures/{capture_id}/artifact/server_parsed.json",
        }
        if has_markdown_view:
            urls["server_parsed_markdown"] = (
                f"{base}/captures/{capture_id}/artifact/server_parsed_markdown.json"
            )
        if enriched:
            urls["enrichment"] = f"{base}/captures/{capture_id}/artifact/enrichment.json"
        return urls

    def create(self, request: HttpRequest) -> Response:
        data = CaptureInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payload = cast(CapturePayload, data.validated_data)
        extraction = payload["extraction"]

        capture_id = f"c_{uuid.uuid4().hex}"
        capture = self._create_capture_record(capture_id, payload)

        raw_references = extraction.get("references")
        references = cast(list[ReferencePayload] | None, raw_references if isinstance(raw_references, list) else None)
        self._seed_client_references(capture, references)
        self._apply_head_doi(capture)
        self._write_initial_artifacts(capture)

        enrichment_blob = self._apply_doi_enrichment(capture)

        parsed = parse_with_fallback(capture.url, capture.content_html, capture.dom_html)
        content_sections = self._reconcile_parser_results(capture, parsed)

        final_state = CaptureOutSerializer(capture).data
        write_json_artifact(capture.id, "parsed.json", final_state)

        serialized_refs = [
            _reference_to_server_view(ref)
            for ref in (final_state.get("references") or [])
        ]

        markdown_view = _build_markdown_capture_view(
            content=content_sections,
            meta=final_state.get("meta"),
            references=serialized_refs,
            title=capture.title,
        )

        server_view = {
            "id": capture.id,
            "url": capture.url,
            "meta": capture.meta,
            "reference_count": len(serialized_refs),
            "references": serialized_refs,
            "enriched": bool(enrichment_blob),
        }
        if content_sections:
            server_view["content"] = content_sections
        if markdown_view:
            server_view["content_markdown"] = markdown_view
        write_json_artifact(capture.id, "server_parsed.json", server_view)
        if markdown_view:
            write_json_artifact(capture.id, "server_parsed_markdown.json", markdown_view)

        artifact_urls = self._build_artifact_urls(
            request,
            capture.id,
            bool(enrichment_blob),
            bool(markdown_view),
        )

        refs_qs = capture.references.all()[:3]
        summary = {
            "title": capture.title,
            "url": capture.url,
            "reference_count": capture.references.count(),
            "figure_count": len(capture.figures or []),
            "table_count": len(capture.tables or []),
            "first_3_references": [{"apa": r.apa, "doi": r.doi} for r in refs_qs],
        }
        return Response(
            {"capture_id": capture_id, "summary": summary, "artifacts": artifact_urls},
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request: HttpRequest, pk: str | None = None) -> Response:
        from django.shortcuts import get_object_or_404
        cap = get_object_or_404(Capture, pk=pk)
        return Response(CaptureOutSerializer(cap).data)

    def list(self, request: HttpRequest) -> Response:
        qs = Capture.objects.order_by("-captured_at")
        limit = int(request.query_params.get("limit", 20))
        data = [CaptureOutSerializer(c).data for c in qs[:limit]]
        return Response({"results": data, "count": qs.count()})

# ---- Health & enrichment endpoints ----

@api_view(["GET"])
def healthz(_request: HttpRequest) -> Response:
    return Response({"status": "ok"})

@api_view(["POST"])
def enrich_doi(request: HttpRequest, pk: str) -> Response:
    from django.shortcuts import get_object_or_404
    cap = get_object_or_404(Capture, pk=pk)
    result = apply_doi_enrichment(cap, allow_head_lookup=True)

    if result.doi is None:
        return Response({"detail": "No DOI available to enrich."}, status=400)
    if not result.blob:
        return Response({"detail": "Enrichment failed or not found."}, status=502)

    return Response({"ok": True, "meta": cap.meta, "csl": cap.csl})
