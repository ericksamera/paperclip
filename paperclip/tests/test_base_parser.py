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
