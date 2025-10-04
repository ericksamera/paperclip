# services/server/captures/tests/test_parsing_bridge.py
from __future__ import annotations

from django.test import SimpleTestCase

from captures.head_meta import extract_head_meta
from captures.parsing_bridge import robust_parse

DOM_WITH_META = """<!doctype html>
<html>
  <head>
    <meta name="citation_title" content="The Science of Foo">
    <meta name="citation_doi" content="10.1234/abcd.efgh">
    <meta name="prism.publicationdate" content="2021-03-15">
    <meta name="citation_journal_title" content="Journal of Foo">
    <meta name="citation_keywords" content="foo; bar, baz">
  </head>
  <body>
    <article>
      <p>Alpha paragraph.</p>
      <p>Beta paragraph.</p>
    </article>
  </body>
</html>
"""
CONTENT_HTML = """
<div>
  <p>Intro paragraph.</p>
  <p>Second paragraph, with more detail.</p>
</div>
"""
DOM_WITHOUT_CONTENT = """<!doctype html>
<html>
  <head><title>Fallback Title</title></head>
  <body>
    <main>
      <p>Fallback alpha.</p>
      <script>console.log('noise');</script>
      <p>Fallback beta.</p>
    </main>
  </body>
</html>
"""
DOM_WITH_AUTHORS = """<!doctype html>
<html>
  <head>
    <meta name="citation_title" content="Authors Test">
    <meta name="citation_author" content="E. Larcombe">
    <meta name="citation_author" content="M. E. Alexander">
    <meta name="dc.creator" content="D. Snellgrove; F. L. Henriquez; K. A. Sloman">
  </head>
  <body><article><p>Hi</p></article></body>
</html>
"""


class HeadMetaTests(SimpleTestCase):
    def test_extract_head_meta_title_doi_year(self) -> None:
        out = extract_head_meta(DOM_WITH_META)
        self.assertEqual(out.get("title"), "The Science of Foo")
        self.assertEqual(out.get("title_source"), "citation")
        self.assertEqual(out.get("doi"), "10.1234/abcd.efgh")
        self.assertEqual(out.get("issued_year"), 2021)


class RobustParseUnitTests(SimpleTestCase):
    def test_robust_parse_merges_keywords_and_journal_and_builds_preview(self) -> None:
        rv = robust_parse(
            url="https://example.org/foo", content_html=CONTENT_HTML, dom_html=DOM_WITH_META
        )
        meta = rv.get("meta_updates") or {}
        sections = rv.get("content_sections") or {}
        self.assertEqual(meta.get("title"), "The Science of Foo")
        self.assertEqual(meta.get("doi"), "10.1234/abcd.efgh")
        self.assertEqual(meta.get("issued_year"), 2021)
        self.assertEqual(meta.get("container_title"), "Journal of Foo")
        self.assertEqual(meta.get("url"), "https://example.org/foo")
        self.assertEqual(meta.get("keywords"), ["foo", "bar", "baz"])
        paras = sections.get("abstract_or_body") or []
        self.assertGreaterEqual(len(paras), 2)
        self.assertIn("Intro paragraph.", paras[0])
        self.assertIn("Second paragraph", paras[1])

    def test_fallback_to_main_when_no_content_html(self) -> None:
        rv = robust_parse(url=None, content_html="", dom_html=DOM_WITHOUT_CONTENT)
        sections = rv.get("content_sections") or {}
        paras = sections.get("abstract_or_body") or []
        self.assertEqual(paras[:2], ["Fallback alpha.", "Fallback beta."])

    def test_extracts_authors_from_head_meta(self) -> None:
        rv = robust_parse(url=None, content_html="<p>Hi</p>", dom_html=DOM_WITH_AUTHORS)
        meta = rv.get("meta_updates") or {}
        self.assertEqual(
            meta.get("authors"),
            ["E. Larcombe", "M. E. Alexander", "D. Snellgrove", "F. L. Henriquez", "K. A. Sloman"],
        )
