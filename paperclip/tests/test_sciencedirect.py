from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("bs4")

from bs4 import BeautifulSoup

from paperclip.parsers import parse_html, parse_with_fallback
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


SCIENCEDIRECT_BODY_HTML = """
<html>
  <body>
    <section class="Sections" id="body0010">
      <section id="cesec10">
        <h2 class="u-h4">Introduction</h2>
        <div class="u-margin-s-bottom" id="para10">First paragraph with <em>emphasis</em>.</div>
        <div class="u-margin-s-bottom" id="para20">Second paragraph.</div>
      </section>
      <section id="cesec20">
        <h2 class="u-h4">Methods</h2>
        <div class="u-margin-s-bottom">Overview paragraph.</div>
        <section id="cesec20s0005">
          <h3>Sampling</h3>
          <div>Sampling details.</div>
        </section>
        <section id="cesec20s0010">
          <h3>Analysis</h3>
          <div>Analysis paragraph.</div>
        </section>
      </section>
      <section id="cesec30">
        <div class="u-margin-s-bottom">Paragraph without a heading.</div>
      </section>
    </section>
  </body>
</html>
"""


EXPECTED_BODY_SECTIONS = [
    {
        "title": "Introduction",
        "markdown": "First paragraph with *emphasis*.\n\nSecond paragraph.",
        "paragraphs": [
            {
                "type": "paragraph",
                "markdown": "First paragraph with *emphasis*.",
                "sentences": [
                    {"markdown": "First paragraph with *emphasis*.", "citations": []},
                ],
            },
            {
                "type": "paragraph",
                "markdown": "Second paragraph.",
                "sentences": [
                    {"markdown": "Second paragraph.", "citations": []},
                ],
            },
        ],
    },
    {
        "title": "Methods",
        "markdown": "Overview paragraph.",
        "paragraphs": [
            {
                "type": "paragraph",
                "markdown": "Overview paragraph.",
                "sentences": [
                    {"markdown": "Overview paragraph.", "citations": []},
                ],
            }
        ],
        "children": [
            {
                "title": "Sampling",
                "markdown": "Sampling details.",
                "paragraphs": [
                    {
                        "type": "paragraph",
                        "markdown": "Sampling details.",
                        "sentences": [
                            {"markdown": "Sampling details.", "citations": []},
                        ],
                    }
                ],
            },
            {
                "title": "Analysis",
                "markdown": "Analysis paragraph.",
                "paragraphs": [
                    {
                        "type": "paragraph",
                        "markdown": "Analysis paragraph.",
                        "sentences": [
                            {"markdown": "Analysis paragraph.", "citations": []},
                        ],
                    }
                ],
            },
        ],
    },
    {
        "title": "Section 3",
        "markdown": "Paragraph without a heading.",
        "paragraphs": [
            {
                "type": "paragraph",
                "markdown": "Paragraph without a heading.",
                "sentences": [
                    {"markdown": "Paragraph without a heading.", "citations": []},
                ],
            }
        ],
    },
]


SCIENCEDIRECT_BODY_WITH_CITATIONS_HTML = """
<html>
  <body>
    <section class="Sections" id="body0010">
      <section id="cesec10">
        <h2 class="u-h4">Background</h2>
        <div class="u-margin-s-bottom" id="para10">
          Infectious diseases impact productivity (<a class="anchor" href="#bib48" data-xocs-content-id="bib48">Hernandez et al., 2001</a>; <a class="anchor" href="#bib22" data-xocs-content-id="bib22">Chi et al., 2002</a>; <a class="anchor" href="#bib80" data-xocs-content-id="bib80">Ott et al., 2003</a>). In addition, consumer concerns remain (<a class="anchor" href="#bib16" data-xocs-content-id="bib16">Bharti et al., 2003</a>; <a class="anchor" href="#bib8" data-xocs-content-id="bib8">Barkema et al., 2015</a>). Although emerging outbreaks draw attention (<a class="anchor" href="#bib108" data-xocs-content-id="bib108">Wierup, 2012</a>). Several important endemic diseases remain major challenges.
        </div>
      </section>
    </section>
  </body>
</html>
"""


EXPECTED_BODY_WITH_CITATIONS = [
    {
        "title": "Background",
        "markdown": (
            "Infectious diseases impact productivity ([Hernandez et al., 2001](#bib48); [Chi et al., 2002](#bib22); "
            "[Ott et al., 2003](#bib80)). In addition, consumer concerns remain ([Bharti et al., 2003](#bib16); "
            "[Barkema et al., 2015](#bib8)). Although emerging outbreaks draw attention ([Wierup, 2012](#bib108)). "
            "Several important endemic diseases remain major challenges."
        ),
        "paragraphs": [
            {
                "type": "paragraph",
                "markdown": (
                    "Infectious diseases impact productivity ([Hernandez et al., 2001](#bib48); [Chi et al., 2002](#bib22); "
                    "[Ott et al., 2003](#bib80)). In addition, consumer concerns remain ([Bharti et al., 2003](#bib16); "
                    "[Barkema et al., 2015](#bib8)). Although emerging outbreaks draw attention ([Wierup, 2012](#bib108)). "
                    "Several important endemic diseases remain major challenges."
                ),
                "sentences": [
                    {
                        "markdown": "Infectious diseases impact productivity ([Hernandez et al., 2001](#bib48); [Chi et al., 2002](#bib22); [Ott et al., 2003](#bib80)).",
                        "citations": ["bib48", "bib22", "bib80"],
                    },
                    {
                        "markdown": "In addition, consumer concerns remain ([Bharti et al., 2003](#bib16); [Barkema et al., 2015](#bib8)).",
                        "citations": ["bib16", "bib8"],
                    },
                    {
                        "markdown": "Although emerging outbreaks draw attention ([Wierup, 2012](#bib108)).",
                        "citations": ["bib108"],
                    },
                    {
                        "markdown": "Several important endemic diseases remain major challenges.",
                        "citations": [],
                    },
                ],
            }
        ],
    }
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
    meta: dict[str, Any] = {}
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


def test_extracts_body_sections() -> None:
    url = "https://www.sciencedirect.com/science/article/pii/S9876543210987654"
    parsed = parse_html(url, SCIENCEDIRECT_BODY_HTML)
    assert parsed.content_sections["body"] == EXPECTED_BODY_SECTIONS


def test_body_sentences_include_reference_annotations() -> None:
    url = "https://www.sciencedirect.com/science/article/pii/S2468135799999999"
    parsed = parse_html(url, SCIENCEDIRECT_BODY_WITH_CITATIONS_HTML)
    assert parsed.content_sections["body"] == EXPECTED_BODY_WITH_CITATIONS


SCIENCEDIRECT_REFERENCES_HTML = """
<html>
  <body>
    <section class="bibliography u-font-serif text-s" id="bi0010">
      <section class="bibliography-sec" id="bs0010">
        <ol class="references" id="reference-links-bs0010">
          <li>
            <span class="label u-font-sans">
              <a class="anchor anchor-primary" href="#bbb0010" id="ref-id-bb0010">
                <span class="anchor-text-container"><span class="anchor-text">1</span></span>
              </a>
            </span>
            <span class="reference" id="rf0010">
              <div class="contribution">
                <div class="authors u-font-sans">J.S. Bailey, Thomson J.E., Cox N.A.</div>
              </div>
              <div class="host u-font-sans">Academic Press, Orlando, FL (1987)</div>
              <div class="ReferenceLinks u-font-sans">
                <a class="anchor link anchor-primary" href="https://scholar.google.com">Google Scholar</a>
              </div>
            </span>
          </li>
          <li>
            <span class="label u-font-sans">
              <a class="anchor anchor-primary" href="#bbb0015" id="ref-id-bb0015">
                <span class="anchor-text-container"><span class="anchor-text">2</span></span>
              </a>
            </span>
            <span class="reference" id="rf0015">
              <div class="contribution">
                <div class="authors u-font-sans">P. Bird, Fisher K., Boyle M., Huffman T., Benzinger P. Jr</div>
                <div class="title text-m">Evaluation of modification of the 3M™ molecular detection assay Salmonella method</div>
              </div>
              <div class="host u-font-sans">J. AOAC Int, 97 (2014), pp. 1329-1342</div>
              <div class="ReferenceLinks u-font-sans">
                <a class="anchor link anchor-primary" href="https://doi.org/10.5740/jaoacint.14-101">Crossref</a>
                <a class="anchor link anchor-primary" href="https://www.scopus.com">View in Scopus</a>
              </div>
            </span>
          </li>
          <li>
            <span class="label u-font-sans">
              <a class="anchor anchor-primary" href="#bbb0020" id="ref-id-bb0020">
                <span class="anchor-text-container"><span class="anchor-text">3</span></span>
              </a>
            </span>
            <span class="reference" id="rf0020">
              <div class="contribution">
                <div class="authors u-font-sans">A.P.D.R. Brizio, Prentice C.</div>
                <div class="title text-m">Chilled broiler carcasses: prevalence of Salmonella</div>
              </div>
              <div class="host u-font-sans">Journal of Parsing, 12 (3) (2015), pp. 10-20</div>
              <div class="ReferenceLinks u-font-sans">
                <a class="anchor link anchor-primary" href="https://www.example.com/ref3">View article</a>
              </div>
            </span>
          </li>
          <li>
            <span class="label u-font-sans">
              <a class="anchor anchor-primary" href="#bbb0025" id="ref-id-bb0025">
                <span class="anchor-text-container"><span class="anchor-text">4</span></span>
              </a>
            </span>
            <span class="reference" id="rf0025">
              <div class="contribution">
                <div class="authors u-font-sans">Example A., Author B.</div>
                <div class="title text-m">Derived DOI example entry</div>
              </div>
              <div class="host u-font-sans">Sample Journal, 42 (2018), pp. 101-110</div>
              <div class="ReferenceLinks u-font-sans">
                <a class="anchor pdf link anchor-primary anchor-icon-left" href="/science/article/pii/S012345671800567X/pdfft">View PDF</a>
                <a class="anchor link anchor-primary" href="/science/article/pii/S012345671800567X">View article</a>
              </div>
            </span>
          </li>
        </ol>
      </section>
    </section>
  </body>
</html>
"""


def test_structured_references_are_parsed() -> None:
    url = "https://www.sciencedirect.com/science/article/pii/S1111111111111111"
    parsed = parse_html(url, SCIENCEDIRECT_REFERENCES_HTML)
    refs = parsed.references

    assert len(refs) == 4

    first = refs[0]
    assert first.issued_year == "1987"
    assert first.container_title == "Academic Press"
    assert first.authors and first.authors[0]["family"] == "Bailey"

    second = refs[1]
    assert second.title == "Evaluation of modification of the 3M™ molecular detection assay Salmonella method"
    assert second.container_title == "J. AOAC Int"
    assert second.volume == "97"
    assert second.pages == "1329-1342"
    assert second.issued_year == "2014"
    assert second.doi == "10.5740/jaoacint.14-101"

    third = refs[2]
    assert third.container_title == "Journal of Parsing"
    assert third.volume == "12"
    assert third.issue == "3"
    assert third.pages == "10-20"
    assert third.issued_year == "2015"
    assert third.url == "https://www.example.com/ref3"

    fourth = refs[3]
    assert fourth.title == "Derived DOI example entry"
    assert fourth.issued_year == "2018"
    assert fourth.doi == "10.1016/S0123-4567(18)00567-X"


def test_parse_with_fallback_uses_dom_references_when_fragment_is_empty() -> None:
    url = "https://www.sciencedirect.com/science/article/pii/S2222222222222222"
    content_html = """
    <html>
      <body>
        <main>
          <article>
            <p>Article body without reference list.</p>
          </article>
        </main>
      </body>
    </html>
    """

    parsed = parse_with_fallback(url, content_html, SCIENCEDIRECT_REFERENCES_HTML)
    assert len(parsed.references) == 4


def test_detects_proxied_domains() -> None:
    url = "https://www-sciencedirect-com.ezproxy.kpu.ca:2443/science/article/pii/S3333333333333333"
    parsed = parse_html(url, SCIENCEDIRECT_REFERENCES_HTML)

    # When the parser correctly recognises the proxied host it should build the
    # structured fields instead of falling back to the generic heuristic parser.
    assert parsed.references[1].container_title == "J. AOAC Int"
