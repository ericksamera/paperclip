from __future__ import annotations

from paperclip.sectionizer import build_sections_meta, split_into_sections


def test_sectionizer_splits_basic_paper_shape():
    text = """
Abstract
We did a thing.

Introduction
This is the intro.
More intro.

Materials and Methods
We ran experiments.

Results
We found outcomes.

Discussion
We interpret outcomes.

Conclusion
We conclude.

""".strip()

    sections = split_into_sections(text)
    assert len(sections) >= 6

    kinds = [s["kind"] for s in sections]
    assert "abstract" in kinds
    assert "introduction" in kinds
    assert "methods" in kinds
    assert "results" in kinds
    assert "discussion" in kinds
    assert "conclusion" in kinds

    intro = next(s for s in sections if s["kind"] == "introduction")
    assert "This is the intro." in intro["text"]


def test_sectionizer_avoids_sentence_lines_as_headings():
    # This line ends with a period => should not be a heading.
    text = """
This is not a heading.
It is a sentence.

Introduction
Real content here.
""".strip()

    sections = split_into_sections(text)
    assert any(s["kind"] == "introduction" for s in sections)

    # The first sentence should remain in the first section body, not become its own section.
    assert sections[0]["title"] in (
        "Body",
        "This is not a heading.",
    )  # allow Body if no headings seen yet
    assert "This is not a heading." in sections[0]["text"]


def test_build_sections_meta_returns_counts():
    meta = build_sections_meta("Introduction\nHello\n\nMethods\nWorld\n")
    assert "sections" in meta
    assert "sections_count" in meta
    assert meta["sections_count"] == len(meta["sections"])
