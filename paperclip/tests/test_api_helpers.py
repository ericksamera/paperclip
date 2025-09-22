from __future__ import annotations

import os
import threading
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence, cast

import pytest

django = pytest.importorskip("django")
pytest.importorskip("rest_framework")
from rest_framework.test import APIRequestFactory

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "paperclip_srv.settings")
django.setup()

pytest.importorskip("bs4")

import paperclip.api as api_module
from paperclip.api import (
    _build_reduced_capture_view,
    _content_sections_to_markdown_paragraphs,
    _enrich_reference_objs_with_doi,
    _reference_to_server_view,
    apply_doi_enrichment,
)
from paperclip.parsers.base import ReferenceObj


def test_reference_to_server_view_preserves_fields_and_adds_alias() -> None:
    reference = {
        "ref_id": "ref-1",
        "raw": "Raw citation",
        "title": "Sample Title",
        "authors": [{"family": "Doe", "given": "Jane"}],
        "container_title": "Journal Name",
        "issued_year": "2024",
        "volume": "12",
        "issue": "3",
        "pages": "45-67",
        "publisher": "Publishing House",
        "url": "https://example.com/article",
        "doi": "10.1234/example.doi",
        "issn": "1234-5678",
        "isbn": "978-1-23456-789-0",
        "bibtex": "@article{...}",
        "apa": "Doe, J. (2024). Sample Title.",
        "csl": {"type": "article-journal"},
    }

    output = _reference_to_server_view(reference)

    # Ensure the payload is copied (no in-place mutation)
    assert output is not reference
    assert "id" in output and output["id"] == reference["ref_id"]

    for key, value in reference.items():
        assert output[key] == value

    # Original reference should remain untouched by alias injection
    assert "id" not in reference


def test_content_sections_to_markdown_paragraphs_simplifies_structure() -> None:
    content = {
        "abstract": [
            {"title": "Summary", "body": "Overview of findings."},
            {"body": ""},
        ],
        "body": [
            {
                "title": "Introduction",
                "markdown": "Intro paragraph.\n\nSecond intro paragraph.",
                "paragraphs": [
                    {"markdown": "Intro paragraph.", "sentences": []},
                    {"markdown": "Second intro paragraph.", "sentences": []},
                    {"markdown": "", "sentences": []},
                ],
                "children": [
                    {
                        "title": "Background",
                        "paragraphs": [
                            {"markdown": "Background details.", "sentences": []},
                        ],
                    },
                    "ignored",
                ],
            }
        ],
        "keywords": [" methods ", "", "results"],
    }

    simplified = _content_sections_to_markdown_paragraphs(content)

    assert simplified == {
        "abstract": [
            {"title": "Summary", "paragraphs": ["Overview of findings."]},
        ],
        "body": [
            {
                "title": "Introduction",
                "paragraphs": [
                    "Intro paragraph.",
                    "Second intro paragraph.",
                ],
                "children": [
                    {
                        "title": "Background",
                        "paragraphs": ["Background details."],
                    }
                ],
            }
        ],
        "keywords": ["methods", "results"],
    }


def test_content_sections_to_markdown_paragraphs_uses_sentence_fallback() -> None:
    content = {
        "body": [
            {
                "title": "Fallback",
                "paragraphs": [
                    {
                        "markdown": "",
                        "sentences": [
                            {"markdown": "Sentence one."},
                            {"markdown": "Sentence two."},
                        ],
                    },
                    {"sentences": ["Trailing sentence."]},
                ],
            }
        ]
    }

    simplified = _content_sections_to_markdown_paragraphs(content)

    assert simplified["body"] == [
        {
            "title": "Fallback",
            "paragraphs": [
                "Sentence one. Sentence two.",
                "Trailing sentence.",
            ],
        }
    ]


def test_content_sections_to_markdown_paragraphs_handles_text_fields() -> None:
    content = {
        "body": [
            {
                "title": "Various Shapes",
                "paragraphs": [
                    {"markdown": "", "text": "Primary paragraph."},
                    {"content": "Secondary paragraph."},
                    {
                        "markdown": "",
                        "sentences": [
                            {"text": "Sentence alpha"},
                            {"body": "Sentence beta."},
                        ],
                    },
                    {"content": ["Nested", {"text": "content"}]},
                    "Trailing paragraph.",
                ],
            }
        ]
    }

    simplified = _content_sections_to_markdown_paragraphs(content)

    assert simplified["body"] == [
        {
            "title": "Various Shapes",
            "paragraphs": [
                "Primary paragraph.",
                "Secondary paragraph.",
                "Sentence alpha Sentence beta.",
                "Nested content",
                "Trailing paragraph.",
            ],
        }
    ]


def test_content_sections_to_markdown_paragraphs_supports_mapping_paragraphs() -> None:
    content = {
        "body": [
            {
                "title": "Mapping",
                "paragraphs": {
                    "first": {"value": "First paragraph."},
                    "second": {
                        "content": [
                            {"text": "Second"},
                            {"plain": "paragraph."},
                        ]
                    },
                },
            }
        ]
    }

    simplified = _content_sections_to_markdown_paragraphs(content)

    assert simplified["body"] == [
        {
            "title": "Mapping",
            "paragraphs": [
                "First paragraph.",
                "Second paragraph.",
            ],
        }
    ]


def test_build_reduced_capture_view_orders_metadata_and_references() -> None:
    content = {
        "abstract": [
            {"title": "Summary", "body": "Overview."},
        ],
        "keywords": ["science"],
        "body": [
            {
                "title": "Intro",
                "paragraphs": [
                    {"markdown": "Paragraph one."},
                ],
            }
        ],
    }
    meta = {"title": "Sample", "authors": ["Doe"]}
    references = [
        {"ref_id": "ref-1", "raw": "Reference 1."},
        "ignored",
        {"ref_id": "ref-2", "raw": "Reference 2."},
    ]

    view = _build_reduced_capture_view(
        content=content,
        meta=meta,
        references=cast(Sequence[Mapping[str, Any]], references),
        title="Sample",
    )

    assert list(view.keys()) == [
        "metadata",
        "abstract",
        "body",
        "keywords",
        "references",
    ]
    assert view["metadata"] == meta
    assert view["abstract"][0]["paragraphs"] == ["Overview."]
    assert view["body"][0]["paragraphs"] == ["Paragraph one."]
    assert len(view["references"]) == 2
    assert view["references"][0]["ref_id"] == "ref-1"
    assert "markdown" not in view


def test_content_sections_to_markdown_paragraphs_coerces_nested_body_sections() -> None:
    content = {
        "body": {
            "sections": [
                {
                    "title": "Nested Intro",
                    "paragraphs": [
                        {"markdown": "Intro paragraph."},
                    ],
                }
            ]
        }
    }

    simplified = _content_sections_to_markdown_paragraphs(content)

    assert simplified["body"] == [
        {"title": "Nested Intro", "paragraphs": ["Intro paragraph."]}
    ]


def test_content_sections_to_markdown_paragraphs_handles_abstract_containers() -> None:
    content = {
        "abstract": {
            "sections": [
                {"title": "Overview", "body": " Summary of work.  "},
                {"title": "Ignored", "paragraphs": []},
            ]
        }
    }

    simplified = _content_sections_to_markdown_paragraphs(content)

    assert simplified["abstract"] == [
        {"title": "Overview", "paragraphs": ["Summary of work."]}
    ]


def _sample_csl() -> dict:
    return {
        "title": "Filled Title",
        "container-title": "Journal Name",
        "author": [
            {"family": "White", "given": "P.B."},
            {"family": "Doe", "given": "Jane"},
        ],
        "issued": {"date-parts": [[1930, 1, 1]]},
        "volume": "29",
        "issue": "4",
        "page": "443-445",
        "publisher": "Example Publisher",
        "URL": "https://doi.org/10.1017/s0022172400010184",
        "DOI": "10.1017/S0022172400010184",
        "ISSN": ["0022-1724"],
    }


def test_enrich_reference_objs_with_doi_populates_missing_fields() -> None:
    ref = ReferenceObj(id="ref-1", raw="raw ref", doi="10.1017/S0022172400010184")

    calls = []

    def fake_fetch(doi: str):
        calls.append(doi)
        return {"csl": _sample_csl()}

    _enrich_reference_objs_with_doi([ref], fetcher=fake_fetch)

    assert calls == ["10.1017/s0022172400010184"]
    assert ref.title == "Filled Title"
    assert ref.container_title == "Journal Name"
    assert ref.issued_year == "1930"
    assert ref.volume == "29"
    assert ref.pages == "443-445"
    assert ref.publisher == "Example Publisher"
    assert ref.url == "https://doi.org/10.1017/s0022172400010184"
    assert ref.authors and ref.authors[0]["family"] == "White"
    assert ref.issn == "0022-1724"


def test_enrich_reference_objs_with_doi_uses_cache() -> None:
    ref1 = ReferenceObj(id="ref-1", raw="raw1", doi="10.1017/S0022172400010184")
    ref2 = ReferenceObj(id="ref-2", raw="raw2", doi="10.1017/S0022172400010184")

    calls = []

    def fake_fetch(doi: str):
        calls.append(doi)
        return {"csl": _sample_csl()}

    _enrich_reference_objs_with_doi([ref1, ref2], fetcher=fake_fetch)

    assert calls == ["10.1017/s0022172400010184"]
    assert ref2.title == "Filled Title"


def test_enrich_reference_objs_with_doi_skips_when_fields_present() -> None:
    ref = ReferenceObj(
        id="ref-1",
        raw="raw",
        doi="10.1017/S0022172400010184",
        title="Existing",
        authors=[{"family": "Doe", "given": "Jane"}],
        container_title="Journal",
        issued_year="1930",
        volume="29",
        issue="1",
        pages="1-2",
        publisher="Pub",
        url="https://example.com",
    )

    def fake_fetch(doi: str):
        raise AssertionError("fetcher should not be called")

    _enrich_reference_objs_with_doi([ref], fetcher=fake_fetch)


def test_enrich_reference_objs_with_doi_fetches_unique_dois_once() -> None:
    ref1 = ReferenceObj(id="ref-1", raw="raw1", doi="10.1017/S0022172400010184")
    ref2 = ReferenceObj(id="ref-2", raw="raw2", doi="10.1093/ps/81.10.1598")

    calls: list[tuple[str, str]] = []

    def fake_fetch(doi: str):
        calls.append((doi, threading.current_thread().name))
        return {"csl": _sample_csl()}

    attr_name = "REFERENCE_DOI_ENRICHMENT_MAX_WORKERS"
    settings_obj = api_module.settings
    had_attr = hasattr(settings_obj, attr_name)
    prev_workers = getattr(settings_obj, attr_name, None)
    setattr(settings_obj, attr_name, 8)
    try:
        _enrich_reference_objs_with_doi([ref1, ref2], fetcher=fake_fetch)
    finally:
        if had_attr:
            setattr(settings_obj, attr_name, prev_workers)
        else:
            delattr(settings_obj, attr_name)

    normalized_calls = sorted(doi for doi, _ in calls)
    assert normalized_calls == [
        "10.1017/s0022172400010184",
        "10.1093/ps/81.10.1598",
    ]
    assert len(calls) == 2


def test_seed_client_references_bulk_creates(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyReference:
        capture: Any
        raw: Any
        title: Any
        issn: Any

        class Manager:
            def __init__(self) -> None:
                self.created: list[DummyReference] | None = None

            def bulk_create(self, objs: Iterable[DummyReference]) -> None:
                self.created = list(objs)

        objects = Manager()

        def __init__(self, **kwargs: object) -> None:
            self.__dict__.update(kwargs)

    monkeypatch.setattr(api_module, "Reference", DummyReference)

    capture = cast(api_module.Capture, _StubCapture())
    payloads: list[api_module.ReferencePayload] = [
        {"id": "r1", "raw": "Raw ref"},
        {"id": "r2", "raw": "Other", "title": "Title"},
    ]

    viewset = api_module.CaptureViewSet()
    viewset._seed_client_references(capture, payloads)

    created = DummyReference.objects.created
    assert created is not None and len(created) == 2
    first, second = created
    assert first.capture is capture
    assert first.raw == "Raw ref"
    assert first.title == ""
    assert first.issn == ""
    assert second.title == "Title"


class _StubCapture(SimpleNamespace):
    saved_fields: list[list[str]]

    def __init__(self, **kwargs: object) -> None:
        defaults: dict[str, object] = {
            "id": "cap-1",
            "meta": {},
            "dom_html": "",
            "csl": {},
            "title": "",
        }
        defaults.update(kwargs)
        super().__init__(**defaults)
        self.saved_fields = []

    def save(self, *, update_fields: list[str]) -> None:  # type: ignore[override]
        self.saved_fields.append(update_fields)


def test_apply_doi_enrichment_updates_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _StubCapture(meta={"doi": "10.1234/ABC"})

    payload: api_module.EnrichmentPayload = {
        "source": "crossref",
        "csl": {"title": "Updated", "DOI": "10.1234/abc"},
        "raw": {},
    }

    calls: list[str] = []

    def fake_enrich(doi: str) -> api_module.EnrichmentPayload:
        calls.append(doi)
        return payload

    monkeypatch.setattr(api_module, "enrich_from_doi", fake_enrich)
    monkeypatch.setattr(api_module, "write_json_artifact", lambda *_: None)
    monkeypatch.setattr(api_module, "csl_to_doc_meta", lambda csl: {"title": csl.get("title"), "doi": csl.get("DOI")})

    result = apply_doi_enrichment(cast(api_module.Capture, capture))

    assert calls == ["10.1234/abc"]
    assert result.blob == payload
    assert result.doi == "10.1234/abc"
    assert capture.title == "Updated"
    assert capture.meta["title"] == "Updated"
    assert capture.meta["doi"] == "10.1234/abc"
    assert capture.saved_fields == [["csl", "meta", "title"]]


def test_apply_doi_enrichment_with_head_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _StubCapture(meta={}, dom_html="<html></html>")

    payload: api_module.EnrichmentPayload = {
        "source": "crossref",
        "csl": {"title": "From Head", "DOI": "10.5555/head"},
        "raw": {},
    }

    monkeypatch.setattr(api_module.BaseParser, "find_doi_in_meta", lambda _soup: "10.5555/HEAD")
    monkeypatch.setattr(api_module, "enrich_from_doi", lambda doi: payload if doi == "10.5555/head" else None)
    monkeypatch.setattr(api_module, "write_json_artifact", lambda *_: None)
    monkeypatch.setattr(api_module, "csl_to_doc_meta", lambda csl: {"title": csl.get("title"), "doi": csl.get("DOI")})

    result = apply_doi_enrichment(cast(api_module.Capture, capture), allow_head_lookup=True)

    assert result.doi == "10.5555/head"
    assert result.blob == payload
    assert capture.title == "From Head"


def test_apply_head_doi_normalizes_and_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _StubCapture(meta={}, dom_html="<html></html>")

    monkeypatch.setattr(api_module.BaseParser, "find_doi_in_meta", lambda _soup: "10.5555/HEAD")

    viewset = api_module.CaptureViewSet()

    viewset._apply_head_doi(cast(api_module.Capture, capture))

    assert capture.meta == {"doi": "10.5555/head"}
    assert capture.saved_fields == [["meta"]]


def test_apply_head_doi_ignores_unparsable_values(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _StubCapture(meta={}, dom_html="<html></html>")

    monkeypatch.setattr(api_module.BaseParser, "find_doi_in_meta", lambda _soup: "not-a-doi")

    viewset = api_module.CaptureViewSet()

    viewset._apply_head_doi(cast(api_module.Capture, capture))

    assert capture.meta == {}
    assert capture.saved_fields == []


def test_apply_doi_enrichment_without_doi(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _StubCapture(meta={})
    monkeypatch.setattr(api_module, "enrich_from_doi", lambda *_: (_ for _ in ()).throw(AssertionError("should not fetch")))

    result = apply_doi_enrichment(cast(api_module.Capture, capture))

    assert result.doi is None
    assert result.blob is None


def test_enrich_doi_endpoint_handles_missing_and_failed_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = APIRequestFactory()
    request = factory.post("/captures/cap/enrich-doi/", {})

    capture = _StubCapture(id="cap", meta={})

    monkeypatch.setattr("django.shortcuts.get_object_or_404", lambda model, pk: capture)

    monkeypatch.setattr(
        api_module,
        "apply_doi_enrichment",
        lambda _capture, allow_head_lookup: api_module.DoiEnrichmentResult(blob=None, doi=None),
    )

    response = api_module.enrich_doi(request, pk="cap")
    assert response.status_code == 400

    monkeypatch.setattr(
        api_module,
        "apply_doi_enrichment",
        lambda _capture, allow_head_lookup: api_module.DoiEnrichmentResult(blob=None, doi="10.1/abc"),
    )

    response = api_module.enrich_doi(request, pk="cap")
    assert response.status_code == 502


def test_enrich_doi_endpoint_success(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = APIRequestFactory()
    request = factory.post("/captures/cap/enrich-doi/", {})

    capture = _StubCapture(id="cap", meta={}, csl={})

    monkeypatch.setattr("django.shortcuts.get_object_or_404", lambda model, pk: capture)

    payload: api_module.EnrichmentPayload = {
        "source": "crossref",
        "csl": {"title": "Updated"},
        "raw": {},
    }

    def fake_apply(_capture: _StubCapture, allow_head_lookup: bool) -> api_module.DoiEnrichmentResult:
        _capture.meta = {"title": "Updated"}
        _capture.csl = payload["csl"]
        return api_module.DoiEnrichmentResult(blob=payload, doi="10.1/abc")

    monkeypatch.setattr(api_module, "apply_doi_enrichment", fake_apply)

    response = api_module.enrich_doi(request, pk="cap")
    assert response.status_code == 200
    assert response.data == {"ok": True, "meta": {"title": "Updated"}, "csl": {"title": "Updated"}}
