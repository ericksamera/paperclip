from __future__ import annotations

from typing import cast

from django.test import SimpleTestCase

from captures.site_parsers import extract_references

PMC_SNIPPET = """
<section class="ref-list">
  <ul class="ref-list">
    <li id="B1">
      <cite>Foreman CM ... 2013. Environ Res Lett 8:035022.
      doi: 10.1088/1748-9326/8/3/035022</cite>
    </li>
    <li id="B2">
      <cite>Smith HJ ... 2018. FEMS Microbiol Ecol 94:fiy090.
      doi: 10.1093/femsec/fiy090</cite>
    </li>
    <li id="B3"><cite>William S ... 2012. Sigma 50:6876.</cite></li>
  </ul>
</section>
"""


class PMCSiteParserTests(SimpleTestCase):
    def test_pmc_extracts_three(self) -> None:
        url = "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567/"
        refs = extract_references(url, PMC_SNIPPET)
        self.assertEqual(len(refs), 3)
        doi = cast(str, refs[0]["doi"])
        self.assertIn("10.1088/1748-9326/8/3/035022", doi)
        self.assertEqual(refs[1]["issued_year"], "2018")

    def test_pmc_subdomain_also_extracts_three(self) -> None:
        url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/"
        refs = extract_references(url, PMC_SNIPPET)
        self.assertEqual(len(refs), 3)
