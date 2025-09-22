import pytest

pytest.importorskip("bs4")

from paperclip.parsers.base import ReferenceObj


def test_reference_from_csl_normalizes_authors_and_identifiers() -> None:
    csl = {
        "title": "Sample",
        "author": {"family": "Doe", "given": "Jane"},
        "DOI": ["10.1234/Example"],
        "ISSN": ["1234-5678", "9876-5432"],
        "ISBN": ("1111-2222", "3333-4444"),
        "volume": ("12",),
        "issue": ["3"],
        "page": ("45-67",),
        "publisher": ["Publishing House"],
        "URL": ("https://example.com/article",),
    }

    ref = ReferenceObj.from_csl("Raw citation", csl, id="ref-1")

    assert ref.id == "ref-1"
    assert ref.authors == [{"family": "Doe", "given": "Jane"}]
    assert ref.doi == "10.1234/Example"
    assert ref.issn == "1234-5678"
    assert ref.isbn == "1111-2222"
    assert ref.volume == "12"
    assert ref.issue == "3"
    assert ref.pages == "45-67"
    assert ref.publisher == "Publishing House"
    assert ref.url == "https://example.com/article"


def test_reference_from_csl_normalizes_scalar_numbers() -> None:
    csl = {
        "title": "Numeric Volume",
        "volume": 7,
        "issue": 2,
        "page": (1, 10),
    }

    ref = ReferenceObj.from_csl("Raw", csl, id=None)

    assert ref.volume == "7"
    assert ref.issue == "2"
    assert ref.pages == "1"


def test_reference_from_raw_handles_spaced_year_and_page_range() -> None:
    raw = (
        "Brackelsberg, C.A. , Nolan, L.K. and Brown, J. ( 1997 ) Characterization of Salmonella "
        "Dublin and Salmonella Typhimurium (Copenhagen) isolates from cattle . Veterinary Research "
        "Communications 21 , 409 – 420 . 10.1023/A:1005803301827"
    )

    ref = ReferenceObj.from_raw_heuristic(raw, id="ref-1")

    assert ref.id == "ref-1"
    assert ref.issued_year == "1997"
    assert ref.volume == "21"
    assert ref.pages == "409 – 420"
    assert ref.doi == "10.1023/A:1005803301827"
    assert len(ref.authors) == 3
    assert ref.authors[0] == {"family": "Brackelsberg", "given": "C.A"}
