from __future__ import annotations

import pytest

pytest.importorskip("bs4")

from bs4 import BeautifulSoup

from paperclip.parsers import parse_html
from paperclip.parsers.sites.wiley import WileyParser

WILEY_SAMPLE_HTML = """
<html>
  <body>
    <div class="abstract-group metis-abstract">
      <section class="article-section article-section__abstract" lang="en" data-lang="en" lang-name="English" id="section-1-en">
        <h2 id="d48575174" class="article-section__header section__title main abstractlang_en main">Abstract</h2>
        <div class="article-section__content en main">
          <p>Double-digest Restriction-site Associated DNA sequencing (ddRADseq) is widely used to generate genomic data for non-model organisms in evolutionary and ecological studies. Along with affordable paired-end sequencing, this method makes population genomic analyses more accessible. However, multiple factors should be considered when designing a ddRADseq experiment, which can be challenging for new users. The generated data often suffer from substantial read overlaps and adaptor contamination, severely reducing sequencing efficiency and affecting data quality. Here, we analyse diverse datasets from the literature and carry out controlled experiments to understand the effects of enzyme choice and size selection on sequencing efficiency. The empirical data reveal that size selection is imprecise and has limited efficacy. In certain scenarios, a substantial proportion of short fragments pass below the lower size-selection cut-off resulting in low sequencing efficiency. However, enzyme choice can considerably mitigate inadvertent inclusion of these shorter fragments. A simple model based on these experiments is implemented to predict the number of genomic fragments generated after digestion and size selection, number of SNPs genotyped, number of samples that can be multiplexed and the expected sequencing efficiency. We developed ddgRADer – http://ddgrader.haifa.ac.il.ezproxy.kpu.ca:2080/ – a user-friendly webtool and incorporated these calculations to aid in ddRADseq experimental design while optimizing sequencing efficiency. This tool can also be used for single enzyme protocols such as Genotyping-by-Sequencing. Given user-defined study goals, ddgRADer recommends enzyme pairs and allows users to compare and choose enzymes and size-selection criteria. ddgRADer improves the accessibility and ease of designing ddRADseq experiments and increases the probability of success of the first population genomic study conducted in labs with no prior experience in genomics.</p>
        </div>
      </section>
    </div>
  </body>
</html>
"""

EXPECTED_ABSTRACT = [
    {
        "title": None,
        "body": (
            "Double-digest Restriction-site Associated DNA sequencing (ddRADseq) is widely used to generate genomic data "
            "for non-model organisms in evolutionary and ecological studies. Along with affordable paired-end sequencing, "
            "this method makes population genomic analyses more accessible. However, multiple factors should be considered "
            "when designing a ddRADseq experiment, which can be challenging for new users. The generated data often suffer "
            "from substantial read overlaps and adaptor contamination, severely reducing sequencing efficiency and affecting "
            "data quality. Here, we analyse diverse datasets from the literature and carry out controlled experiments to "
            "understand the effects of enzyme choice and size selection on sequencing efficiency. The empirical data reveal "
            "that size selection is imprecise and has limited efficacy. In certain scenarios, a substantial proportion of "
            "short fragments pass below the lower size-selection cut-off resulting in low sequencing efficiency. However, "
            "enzyme choice can considerably mitigate inadvertent inclusion of these shorter fragments. A simple model based "
            "on these experiments is implemented to predict the number of genomic fragments generated after digestion and size "
            "selection, number of SNPs genotyped, number of samples that can be multiplexed and the expected sequencing "
            "efficiency. We developed ddgRADer – http://ddgrader.haifa.ac.il.ezproxy.kpu.ca:2080/ – a user-friendly webtool "
            "and incorporated these calculations to aid in ddRADseq experimental design while optimizing sequencing efficiency. "
            "This tool can also be used for single enzyme protocols such as Genotyping-by-Sequencing. Given user-defined study "
            "goals, ddgRADer recommends enzyme pairs and allows users to compare and choose enzymes and size-selection criteria. "
            "ddgRADer improves the accessibility and ease of designing ddRADseq experiments and increases the probability of "
            "success of the first population genomic study conducted in labs with no prior experience in genomics."
        ),
    }
]

STRUCTURED_WILEY_HTML = """
<html>
  <body>
    <div class="abstract-group  metis-abstract">
      <section class="article-section article-section__abstract" lang="en" data-lang="en" lang-name="English" id="section-1-en">
         <h2 id="d7243088" class="article-section__header section__title main abstractlang_en main">Abstract</h2>
         <div class="article-section__content en main">
            <p><b>Aims:</b> To assess the degree of genetic diversity among animal <i>Salmonella</i> Dublin UK isolates, and to compare it with the genetic diversity found among human isolates from the same time period.</p>
            <p><b>Methods and Results:</b> One hundred isolates (50 human and 50 animal) were typed using plasmid profiling, <i>Xba</i>I-pulsed field gel electrophoresis (PFGE) and <i>Pst</i>I-<i>Sph</i>I ribotyping. Antimicrobial resistance data to 16 antibiotics was presented, and the presence of class-I integrons was investigated by real-time PCR. Seven different plasmid profiles, 19 ribotypes and 21 PFGE types were detected. A combination of the three methods allowed clear differentiation of 43 clones or strains. Eighteen isolates were resistant to at least one antimicrobial; five of them were multi-resistant and of these, only three presented class I integrons.</p>
            <p><b>Conclusions:</b> Ribotyping data suggest the existence of at least three very different clonal lines; the same distribution in well-defined groups was not evident from the PFGE data. The existence of a variety of clones in both animals and humans has been demonstrated. A few prevalent clones seem to be widely disseminated among different animal species and show a diverse geographical and temporal distribution. The same clones were found in animals and humans, which may infer that both farm and pet animals may act as potential vehicles of infection for humans. Some other clones seem to be less widely distributed. Clustering analysis of genomic fingerprints of <i>Salmonella</i> Dublin and <i>Salm.</i> Enteritidis isolates confirms the existence of a close phylogenetic relationship between both serotypes.</p>
            <p><b>Significance and Impact of the Study:</b> This paper describes the utility of a multiple genetic typing approach for <i>Salm.</i> Dublin. It gives useful information on clonal diversity among human and animal isolates.</p>
         </div>
      </section>
   </div>
  </body>
</html>
"""

STRUCTURED_EXPECTED_ABSTRACT = [
    {
        "title": None,
        "body": (
            "Aims: To assess the degree of genetic diversity among animal Salmonella Dublin UK isolates, and to compare it with the genetic diversity found among human isolates from the same time period. "
            "Methods and Results: One hundred isolates (50 human and 50 animal) were typed using plasmid profiling, Xba I-pulsed field gel electrophoresis (PFGE) and Pst I-Sph I ribotyping. Antimicrobial resistance data to 16 antibiotics was presented, and the presence of class-I integrons was investigated by real-time PCR. "
            "Seven different plasmid profiles, 19 ribotypes and 21 PFGE types were detected. A combination of the three methods allowed clear differentiation of 43 clones or strains. Eighteen isolates were resistant to at least one antimicrobial; five of them were multi-resistant and of these, only three presented class I integrons. "
            "Conclusions: Ribotyping data suggest the existence of at least three very different clonal lines; the same distribution in well-defined groups was not evident from the PFGE data. The existence of a variety of clones in both animals and humans has been demonstrated. A few prevalent clones seem to be widely disseminated among different animal species and show a diverse geographical and temporal distribution. "
            "The same clones were found in animals and humans, which may infer that both farm and pet animals may act as potential vehicles of infection for humans. Some other clones seem to be less widely distributed. Clustering analysis of genomic fingerprints of Salmonella Dublin and Salm. Enteritidis isolates confirms the existence of a close phylogenetic relationship between both serotypes. "
            "Significance and Impact of the Study: This paper describes the utility of a multiple genetic typing approach for Salm. Dublin. It gives useful information on clonal diversity among human and animal isolates."
        ),
    }
]


def test_wiley_parser_extracts_abstract_from_article_section() -> None:
    soup = BeautifulSoup(WILEY_SAMPLE_HTML, "html.parser")
    abstract = WileyParser._extract_abstract(soup)
    assert abstract == EXPECTED_ABSTRACT


def test_wiley_content_sections_include_abstract_for_server_view() -> None:
    url = "https://onlinelibrary.wiley.com/doi/10.1002/example"
    parsed = parse_html(url, WILEY_SAMPLE_HTML)
    assert parsed.content_sections["abstract"] == EXPECTED_ABSTRACT


def test_wiley_parser_handles_structured_paragraphs() -> None:
    soup = BeautifulSoup(STRUCTURED_WILEY_HTML, "html.parser")
    abstract = WileyParser._extract_abstract(soup)
    assert abstract == STRUCTURED_EXPECTED_ABSTRACT


def test_wiley_parser_detects_proxied_domains_for_server_capture() -> None:
    proxied_url = "https://onlinelibrary-wiley-com.ezproxy.example.edu/doi/full/10.1002/example"
    parsed = parse_html(proxied_url, STRUCTURED_WILEY_HTML)
    assert parsed.content_sections["abstract"] == STRUCTURED_EXPECTED_ABSTRACT
