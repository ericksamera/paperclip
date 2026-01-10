from __future__ import annotations

from bs4 import BeautifulSoup

from paperclip.parsers.pmc.sections import pmc_sections_from_html
from paperclip.sectionizer import split_into_sections


def test_sectionizer_splits_basic_paper_shape():
    text = """
Abstract
We did a thing.

Keywords: salmonella, fimbriae

Introduction
This is the intro.
""".strip()

    sections = split_into_sections(text)
    kinds = [s["kind"] for s in sections]
    assert "abstract" in kinds
    assert "keywords" in kinds
    assert "introduction" in kinds

    # kinds[] always present
    assert all(isinstance(s.get("kinds"), list) and s["kinds"] for s in sections)


def test_sectionizer_classifies_numbered_introduction_and_keeps_number():
    text = """
1. Introduction
Hello world.
""".strip()

    sections = split_into_sections(text)
    assert len(sections) == 1
    assert sections[0]["kind"] == "introduction"
    assert sections[0]["kinds"] == ["introduction"]
    assert sections[0]["title"] == "Introduction"
    assert sections[0]["number"] == "1"
    assert "Hello world." in sections[0]["text"]


def test_sectionizer_results_and_discussion_gets_multi_kinds():
    text = """
Results and Discussion
We saw a thing.
""".strip()

    sections = split_into_sections(text)
    assert len(sections) == 1
    assert sections[0]["kind"] == "results_discussion"
    assert sections[0]["kinds"] == ["results", "discussion"]


def test_pmc_sections_from_html_classifies_numbered_introduction_and_sets_kinds():
    html = """
    <section class="body main-article-body">
      <section id="s1">
        <h2 class="pmc_sec_title">1. Introduction</h2>
        <p>Intro text.</p>
      </section>
    </section>
    """.strip()

    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("section.body")
    assert body is not None

    secs = pmc_sections_from_html(body)
    assert len(secs) == 1
    assert secs[0]["kind"] == "introduction"
    assert secs[0]["kinds"] == ["introduction"]
    assert secs[0]["title"] == "Introduction"
    assert secs[0]["number"] == "1"
    assert "Intro text." in secs[0]["text"]
