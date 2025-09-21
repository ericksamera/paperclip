from __future__ import annotations

import threading

import pytest

pytest.importorskip("bs4")

import paperclip.api as api_module
from paperclip.api import _reference_to_server_view, _enrich_reference_objs_with_doi
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
