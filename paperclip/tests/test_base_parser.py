from __future__ import annotations

import pytest

pytest.importorskip("bs4")

from bs4 import BeautifulSoup

from paperclip.parsers import parse_html
from paperclip.parsers.sites.generic import GenericParser


def test_generic_parser_extracts_abstract_via_base_helpers() -> None:
    html = """
    <html>
      <body>
        <section class="abstract">
          <h2>Abstract</h2>
          <p>This is a summary.</p>
          <p>It spans multiple paragraphs.</p>
        </section>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")

    abstract = GenericParser._extract_abstract(soup)
    assert abstract == [
        {
            "title": None,
            "body": "This is a summary. It spans multiple paragraphs.",
        }
    ]

    parsed = parse_html("https://example.com/article", html)
    assert parsed.content_sections["abstract"] == abstract
    assert "abstract" not in parsed.meta_updates


def test_generic_parser_preserves_structured_abstract_sections() -> None:
    html = """
    <html>
      <body>
        <section class="abstract">
          <div class="sec">
            <div class="title">Motivation</div>
            <p>Paragraph one.</p>
            <p>Paragraph two.</p>
          </div>
          <div class="sec">
            <div class="title">Results</div>
            <p>Result paragraph.</p>
          </div>
          <div class="sec">
            <div class="title">Availability and implementation</div>
            <p>Availability paragraph.</p>
          </div>
        </section>
      </body>
    </html>
    """

    expected = [
        {"title": "Motivation", "body": "Paragraph one. Paragraph two."},
        {"title": "Results", "body": "Result paragraph."},
        {
            "title": "Availability and implementation",
            "body": "Availability paragraph.",
        },
    ]

    parsed = parse_html("https://example.com/article", html)
    assert parsed.content_sections["abstract"] == expected


def test_generic_parser_collects_keywords_from_markup() -> None:
    html = """
    <html>
      <body>
        <section class="keywords-section">
          <h2>Keywords</h2>
          <div class="keyword">evolution</div>
          <div class="keyword">phylogeny</div>
          <div class="keyword">biodiversity</div>
        </section>
      </body>
    </html>
    """
    parsed = parse_html("https://example.com/article", html)
    assert parsed.content_sections["keywords"] == [
        "evolution",
        "phylogeny",
        "biodiversity",
    ]


def test_generic_parser_collects_keywords_from_meta_tags() -> None:
    html = """
    <html>
      <head>
        <meta name="citation_keywords" content="machine learning, artificial intelligence; computer vision" />
        <meta property="article:tag" content="neural networks" />
      </head>
      <body></body>
    </html>
    """
    parsed = parse_html("https://example.com/article", html)
    assert parsed.content_sections["keywords"] == [
        "machine learning",
        "artificial intelligence",
        "computer vision",
        "neural networks",
    ]


def test_generic_parser_provides_body_section_fallback() -> None:
    html = """
    <html>
      <body>
        <div class="article-body">
          <section id="sec1">
            <h2>Introduction</h2>
            <p>First paragraph introducing the topic.</p>
          </section>
          <section id="sec2">
            <h2>Methods</h2>
            <p>Details about the approach.</p>
          </section>
        </div>
      </body>
    </html>
    """

    parsed = parse_html("https://example.com/article", html)
    body = parsed.content_sections.get("body")
    assert body is not None
    assert [section["title"] for section in body] == ["Introduction", "Methods"]
    assert body[0]["paragraphs"][0]["markdown"] == "First paragraph introducing the topic."
    assert body[1]["paragraphs"][0]["markdown"] == "Details about the approach."


def test_generic_parser_collects_figures_and_tables() -> None:
    html = """
    <html>
      <body>
        <figure id="fig-1" aria-label="Figure 1">
          <img data-src="https://cdn.example.com/figure1@2x.png" src="https://cdn.example.com/figure1.png" alt="Workflow overview" />
          <figcaption><strong>Figure 1.</strong> Workflow overview with highlighted stages.</figcaption>
        </figure>
        <figure>
          <img src="https://cdn.example.com/figure2.png" alt="Detailed plot" />
          <figcaption>Fig. 2 – Detailed plot of the experiment.</figcaption>
        </figure>
        <div class="article-table-content">
          <header class="article-table-caption"><span class="table-caption__label">Table 1.</span> Summary statistics for each cohort</header>
          <table id="tbl-1">
            <tr><th>Group</th><th>Count</th></tr>
            <tr><td>A</td><td>12</td></tr>
            <tr><td>B</td><td>9</td></tr>
          </table>
        </div>
      </body>
    </html>
    """

    parsed = parse_html("https://example.com/article", html)

    figures = parsed.figures
    assert len(figures) == 2

    first = figures[0]
    assert first["id"] == "fig-1"
    assert first["label"] == "Figure 1"
    assert first["caption"] == "Workflow overview with highlighted stages."
    assert first["images"][0]["src"] == "https://cdn.example.com/figure1@2x.png"
    assert first["images"][0]["alt"] == "Workflow overview"

    second = figures[1]
    assert second["label"] == "Figure 2"
    assert second["caption"] == "Detailed plot of the experiment."

    tables = parsed.tables
    assert len(tables) == 1

    table = tables[0]
    assert table["id"] == "tbl-1"
    assert table["label"] == "Table 1"
    assert table["caption"] == "Summary statistics for each cohort"
    assert "<table" in table["html"].lower()
