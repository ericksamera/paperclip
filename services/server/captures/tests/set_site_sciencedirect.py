from __future__ import annotations
from django.test import SimpleTestCase
from captures.site_parsers import extract_references

SCIENCEDIRECT_SNIPPET = """
<span class="reference" id="sref4">
  <div class="contribution">
    <div class="authors u-font-sans">A.T. Vincent, B. Boyle, N. Derome, S.J. Charette</div>
    <div id="ref-id-sref4" class="title text-m">Improvement in the DNA sequencing of genomes bearing long repeated elements</div>
  </div>
  <div class="host u-font-sans">J&nbsp;Microbiol Methods, 107 (2014), pp. 186-188</div>
  <div class="ReferenceLinks u-font-sans"><a href="/science/article/pii/S0167701214003066">View article</a></div>
</span>
"""

class ScienceDirectParserTests(SimpleTestCase):
    def test_sciencedirect_core_fields(self):
        url = "https://www.sciencedirect.com/science/article/pii/S0167701214003066"
        refs = extract_references(url, SCIENCEDIRECT_SNIPPET)
        self.assertEqual(len(refs), 1)
        r = refs[0]
        self.assertEqual(r["title"], "Improvement in the DNA sequencing of genomes bearing long repeated elements")
        self.assertEqual(r["issued_year"], "2014")
        self.assertEqual(r["container_title"], "J Microbiol Methods")
        self.assertEqual(r["volume"], "107")
        self.assertEqual(r["pages"], "186-188")
        self.assertEqual(r["authors"], ["Vincent, A.T.", "Boyle, B.", "Derome, N.", "Charette, S.J."])
