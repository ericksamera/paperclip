# services/server/captures/tests/test_site_wiley.py
from __future__ import annotations

from django.test import SimpleTestCase

from captures.site_parsers import extract_references

WILEY_PANE_SNIPPET = """
<div id="pane-pcw-references" class="tab__pane article-row-right__panes empty active">
  <div class="separator"><div class="separator references-tab__collection">
    <ul class="rlist separator">
      <li data-bib-id="jfd12505-bib-0001">
        <span class="author">Attéré S.A.</span>, <span class="author">Vincent A.T.</span>,
        <span class="author">Trudel M.</span>,
        <span class="author">Chanut R.</span> &amp;
        <span class="author">Charette S.J.</span>
        (<span class="pubYear">2015</span>)
        <span class="articleTitle">
          Diversity and homogeneity among small plasmids of
          <i>Aeromonas salmonicida</i> subsp.
          <i>salmonicida</i> linked with geographical origin
        </span>. <i>Frontiers in Microbiology</i>
        <span class="vol">6</span>, <span class="pageFirst">1274</span>.
        <div class="extra-links getFTR retractionChecked">
          <span class="hidden data-doi">10.3389/fmicb.2015.01274</span>
        </div>
      </li>
    </ul>
  </div></div>
</div>
"""


class WileyPaneParserTests(SimpleTestCase):
    def test_pane_pcw_references_extracts_core_fields(self) -> None:
        url = "https://onlinelibrary.wiley.com/doi/10.1111/jfd.12505"
        refs = extract_references(url, WILEY_PANE_SNIPPET)
        self.assertEqual(len(refs), 1)
        r = refs[0]
        # Authors in order
        self.assertEqual(
            r.get("authors"),
            ["Attéré S.A.", "Vincent A.T.", "Trudel M.", "Chanut R.", "Charette S.J."],
        )
        # Title
        self.assertEqual(
            r.get("title"),
            (
                "Diversity and homogeneity among small plasmids of "
                "Aeromonas salmonicida subsp. salmonicida linked with "
                "geographical origin"
            ),
        )
        # Journal container from the italic tag following the title
        self.assertEqual(r.get("container_title"), "Frontiers in Microbiology")
        # Year / volume / pages
        self.assertEqual(r.get("year"), 2015)
        self.assertEqual(r.get("volume"), "6")
        self.assertEqual(
            r.get("pages"), "1274"
        )  # only pageFirst present → pages == "1274"
        # DOI from the hidden span
        self.assertEqual(r.get("doi"), "10.3389/fmicb.2015.01274")
        self.assertEqual(r.get("url"), "https://doi.org/10.3389/fmicb.2015.01274")
