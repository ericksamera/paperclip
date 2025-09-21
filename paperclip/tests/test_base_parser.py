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
    assert abstract == "This is a summary. It spans multiple paragraphs."

    parsed = parse_html("https://example.com/article", html)
    assert parsed.meta_updates["abstract"] == abstract
