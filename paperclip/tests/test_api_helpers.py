from __future__ import annotations

import pytest

pytest.importorskip("bs4")

from paperclip.api import _reference_to_server_view


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
