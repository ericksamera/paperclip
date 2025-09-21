import pytest

pytest.importorskip("bs4")

from paperclip.parsers.base import ReferenceObj


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
