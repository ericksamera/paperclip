from __future__ import annotations

import pytest

pytest.importorskip("bs4")

from paperclip.parsers import parse_html


def test_plos_parser_extracts_body_sections_from_toc_divs() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://journals.plos.org/plosone/article?id=10.1371/journal.pone.1234567" />
      </head>
      <body>
        <div id="artText" class="article-text">
          <div id="section1" class="section toc-section">
            <h2>1. Introduction</h2>
            <p>Plant domestication has shaped agriculture.</p>
          </div>
          <div id="section2" class="section toc-section">
            <h2>2. Methods</h2>
            <p>Sequencing was carried out as described previously.</p>
          </div>
        </div>
        <div id="references" class="section references">
          <h2>References</h2>
          <ol class="ref-list">
            <li id="pone.0318105.ref001">1. Smith J. Title of study. <em>Journal</em>. 2023. <a href="https://doi.org/10.1371/journal.pone.0318105">https://doi.org/10.1371/journal.pone.0318105</a></li>
            <li id="pone.0318105.ref002">2. Doe A. Another reference. 2022.</li>
          </ol>
        </div>
      </body>
    </html>
    """

    parsed = parse_html(
        "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.1234567",
        html,
    )

    body = parsed.content_sections.get("body")
    assert body is not None
    assert [section["title"] for section in body] == ["1. Introduction", "2. Methods"]
    assert body[0]["paragraphs"][0]["markdown"] == "Plant domestication has shaped agriculture."
    assert body[1]["paragraphs"][0]["markdown"] == "Sequencing was carried out as described previously."

    references = parsed.references
    assert len(references) == 2
    assert references[0].doi == "10.1371/journal.pone.0318105"
    assert references[0].raw.startswith("1. Smith J.")
