from __future__ import annotations
from django.test import SimpleTestCase
from captures.site_parsers import extract_references, dedupe_references
from captures.site_parsers.base import parse_raw_reference

GENERIC_SNIPPET = """
<ol class="references">
  <li><cite>Eid J. et al. Real-time DNA sequencing ... Science. 2009.</cite>
      <a href="https://doi.org/10.1126/science.1162986">DOI</a>
  </li>
  <li><cite>Bland C. et al. 2007. CRISPR recognition tool (CRT) ... BMC Bioinformatics.</cite></li>
</ol>
"""

RAW_FEMS = "[9] J.G. Emond-Rheault, A.T. Vincent, M.V. Trudel, J. Frey, M. Frenette, S.J. Charette AsaGEI2b: a new variant of a genomic island identified in the Aeromonas salmonicida subsp. salmonicida JF3224 strain isolated from a wild fish in Switzerland FEMS Microbiol Lett, 362 (2015) fnv093 Google Scholar"

class GenericParserTests(SimpleTestCase):
    def test_generic_extract(self):
        refs = extract_references("https://example.org/article/abc", GENERIC_SNIPPET)
        self.assertEqual(len(refs), 2)
        self.assertTrue(refs[0]["doi"].startswith("10.1126/science.1162986"))
        self.assertEqual(refs[1]["issued_year"], "2007")

    def test_raw_parser_best_effort(self):
        r = parse_raw_reference(RAW_FEMS)
        self.assertEqual(r.get("issued_year"), "2015")
        self.assertIn("FEMS Microbiol Lett", r.get("container_title", ""))
        self.assertEqual(r.get("volume"), "362")
        self.assertIn("AsaGEI2b", r.get("title", ""))

    def test_dedupe_by_doi(self):
        refs = [{"raw":"x","doi":"10.1/xyz","issued_year":""},{"raw":"x2","doi":"https://doi.org/10.1/xyz","issued_year":""}]
        out = dedupe_references(refs)
        self.assertEqual(len(out), 1)
