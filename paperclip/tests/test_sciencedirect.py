from __future__ import annotations

import pytest

pytest.importorskip("bs4")

from bs4 import BeautifulSoup

from paperclip.parsers import parse_html
from paperclip.parsers.sites.sciencedirect import ScienceDirectParser

SCIENCEDIRECT_SAMPLE_HTML = """
<html>
  <body>
    <div class="abstract author" id="ceab20">
      <h2 class="section-title">ABSTRACT</h2>
      <div id="ceabs20">
        <div class="u-margin-s-bottom" id="spara80">
          <span>Endemic infectious diseases remain a major challenge for dairy producers worldwide. For effective disease control programs, up-to-date prevalence estimates are of utmost importance. The objective of this study was to estimate the herd-level prevalence of <a href="/topics/agricultural-and-biological-sciences/bovine-leukemia-virus" class="topic-link">bovine leukemia virus</a> (BLV), </span>
          <span><span><a href="/topics/agricultural-and-biological-sciences/salmonella-enterica-subsp-enterica" class="topic-link">Salmonella enterica</a></span></span>
          ssp. <em>enterica</em>
          <span> <a href="/topics/agricultural-and-biological-sciences/serotype" class="topic-link">serovar</a> Dublin (</span>
          <em>Salmonella</em> Dublin), and
          <span><span>Neospora <a href="/topics/agricultural-and-biological-sciences/caninae" class="topic-link">caninum</a></span></span>
          <span><span> in <a href="/topics/agricultural-and-biological-sciences/dairy-herds" class="topic-link">dairy herds</a> in Alberta, Canada, using a serial cross-sectional study design. Bulk </span><a href="/topics/agricultural-and-biological-sciences/milk-tanks" class="topic-link">tank milk</a></span>
          samples from all Alberta dairy farms were collected 4 times, in December 2021 (n = 489), April 2022 (n = 487), July 2022 (n = 487), and October 2022 (n = 480), and tested for antibodies against BLV,
          <em>Salmonella</em> Dublin, and
          <em>N. caninum</em>
          <span> using ELISA. Herd-level apparent prevalence was calculated as positive herds divided by total tested herds at each time point. A mixed-effect modified Poisson regression model was employed to assess the association of prevalence with region, <a href="/topics/agricultural-and-biological-sciences/herd-size" class="topic-link">herd size</a>, herd type, and type of milking system. Apparent prevalence of BLV was 89.4%, 88.7%, 86.9%, and 86.9% in December, April, July, and October, respectively, whereas for </span>
          <em>Salmonella</em> Dublin apparent prevalence was 11.2%, 6.6%, 8.6%, and 8.5%, and for
          <em>N. caninum</em>
          apparent prevalence was 18.2%, 7.4%, 7.8%, and 15.0%.
          <span> For BLV,
            <em>Salmonella</em> Dublin, and
            <em>N. caninum</em>, a total of 91.7%, 15.6%, and 28.1% of herds, respectively, were positive at least once, whereas 82.5%, 3.6%, and 3.0% of herds were ELISA positive at all 4 times. Compared with the north region, central Alberta had a high prevalence (prevalence ratio [PR] = 1.13) of BLV antibody-positive herds, whereas south Alberta had a high prevalence (PR = 2.56) of herds positive for
            <em>Salmonella</em> Dublin antibodies. Furthermore, central (PR = 0.52) and south regions (PR = 0.46) had low prevalence of
            <em>N. caninum</em>-positive herds compared with the north. Hutterite colony herds were more frequently BLV positive (PR = 1.13) but less frequently
            <em>N. caninum</em>-positive (PR = 0.47). Large herds (>7,200 L/d milk delivered ∼>250 cows) were 1.1 times more often BLV positive, whereas small herds (≤3,600 L/d milk delivered ∼≤125 cows) were 3.2 times more often
            <em>N. caninum</em>
            positive. For
            <em>Salmonella</em> Dublin, Hutterite colony herds were less frequently (PR = 0.07) positive than non-colony herds only in medium and large strata but not in small stratum. Moreover, larger herds were more frequently (PR = 2.20)
            <em>Salmonella</em> Dublin-positive than smaller herds only in non-colony stratum but not in colony stratum. Moreover,
            <em>N. caninum</em>
            prevalence was 1.6 times higher on farms with conventional milking systems compared with farms with an automated milking system. These results provide up-to-date information of the prevalence of these infections that will inform investigations of within-herd prevalence of these infections and help in devising evidence-based disease control strategies.
          </span>
        </div>
      </div>
    </div>
    <div class="Keywords u-font-serif">
      <div class="keywords-section" id="cekeyws10">
        <h2 class="section-title u-h4 u-margin-l-top u-margin-xs-bottom">Key words</h2>
        <div class="keyword" id="cekeyw10"><span>bovine leukosis</span></div>
        <div class="keyword" id="cekeyw20"><span>neosporosis</span></div>
        <div class="keyword" id="cekeyw30"><span><em>Salmonella</em> Dublin</span></div>
        <div class="keyword" id="cekeyw40"><span>dairy farms</span></div>
        <div class="keyword" id="cekeyw50"><span>surveillance</span></div>
        <div class="keyword" id="cekeyw60"><span>prevalence</span></div>
      </div>
    </div>
  </body>
</html>
"""

EXPECTED_ABSTRACT = [
    {
        "title": None,
        "body": (
            "Endemic infectious diseases remain a major challenge for dairy producers worldwide. "
            "For effective disease control programs, up-to-date prevalence estimates are of utmost importance. "
            "The objective of this study was to estimate the herd-level prevalence of bovine leukemia virus (BLV), "
            "Salmonella enterica ssp. enterica serovar Dublin (Salmonella Dublin), and Neospora caninum in dairy herds "
            "in Alberta, Canada, using a serial cross-sectional study design. Bulk tank milk samples from all Alberta "
            "dairy farms were collected 4 times, in December 2021 (n = 489), April 2022 (n = 487), July 2022 (n = 487), "
            "and October 2022 (n = 480), and tested for antibodies against BLV, Salmonella Dublin, and N. caninum using ELISA. "
            "Herd-level apparent prevalence was calculated as positive herds divided by total tested herds at each time point. "
            "A mixed-effect modified Poisson regression model was employed to assess the association of prevalence with region, "
            "herd size, herd type, and type of milking system. Apparent prevalence of BLV was 89.4%, 88.7%, 86.9%, and 86.9% in "
            "December, April, July, and October, respectively, whereas for Salmonella Dublin apparent prevalence was 11.2%, 6.6%, "
            "8.6%, and 8.5%, and for N. caninum apparent prevalence was 18.2%, 7.4%, 7.8%, and 15.0%. For BLV, Salmonella Dublin, "
            "and N. caninum, a total of 91.7%, 15.6%, and 28.1% of herds, respectively, were positive at least once, whereas 82.5%, "
            "3.6%, and 3.0% of herds were ELISA positive at all 4 times. Compared with the north region, central Alberta had a high "
            "prevalence (prevalence ratio [PR] = 1.13) of BLV antibody-positive herds, whereas south Alberta had a high prevalence "
            "(PR = 2.56) of herds positive for Salmonella Dublin antibodies. Furthermore, central (PR = 0.52) and south regions "
            "(PR = 0.46) had low prevalence of N. caninum-positive herds compared with the north. Hutterite colony herds were more "
            "frequently BLV positive (PR = 1.13) but less frequently N. caninum-positive (PR = 0.47). Large herds (>7,200 L/d milk "
            "delivered ∼>250 cows) were 1.1 times more often BLV positive, whereas small herds (≤3,600 L/d milk delivered ∼≤125 cows) "
            "were 3.2 times more often N. caninum positive. For Salmonella Dublin, Hutterite colony herds were less frequently (PR = 0.07) "
            "positive than non-colony herds only in medium and large strata but not in small stratum. Moreover, larger herds were more "
            "frequently (PR = 2.20) Salmonella Dublin-positive than smaller herds only in non-colony stratum but not in colony stratum. "
            "Moreover, N. caninum prevalence was 1.6 times higher on farms with conventional milking systems compared with farms with "
            "an automated milking system. These results provide up-to-date information of the prevalence of these infections that will "
            "inform investigations of within-herd prevalence of these infections and help in devising evidence-based disease control strategies."
        ),
    }
]

EXPECTED_KEYWORDS = [
    "bovine leukosis",
    "neosporosis",
    "Salmonella Dublin",
    "dairy farms",
    "surveillance",
    "prevalence",
]


def test_extracts_expected_abstract() -> None:
    soup = BeautifulSoup(SCIENCEDIRECT_SAMPLE_HTML, "html.parser")
    abstract = ScienceDirectParser._extract_abstract(soup)
    assert abstract == EXPECTED_ABSTRACT


def test_extracts_keywords() -> None:
    soup = BeautifulSoup(SCIENCEDIRECT_SAMPLE_HTML, "html.parser")
    keywords = ScienceDirectParser._extract_keywords(soup)
    assert keywords == EXPECTED_KEYWORDS


def test_content_sections_include_abstract_for_server_view() -> None:
    url = "https://www.sciencedirect.com/science/article/pii/S1234567890123456"
    parsed = parse_html(url, SCIENCEDIRECT_SAMPLE_HTML)
    meta = {}
    updates = parsed.meta_updates
    if updates:
        if not meta.get("doi") and updates.get("doi"):
            meta["doi"] = updates["doi"]
        for key, value in updates.items():
            if key == "doi":
                continue
            meta[key] = value
    assert "abstract" not in meta
    assert parsed.content_sections["abstract"] == EXPECTED_ABSTRACT
    assert parsed.content_sections["keywords"] == EXPECTED_KEYWORDS
