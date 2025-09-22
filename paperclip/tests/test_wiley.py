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
    },
]

WILEY_BODY_HTML = """
<html>
<body>
<main>
<section class="article-section__content" id="section-1">
<h2 class="article-section__title section__title">Introduction</h2>
<p>Application of post-Sanger sequencing technologies in ecology has accelerated since the introduction of Restriction site Associated DNA sequencing (RADseq; Baird <i>et&nbsp;al.</i> <a href="#bib-1">2008</a>).</p>
<div class="article-table-content" id="table-1">
<header class="article-table-caption"><span class="table-caption__label">Table 1.</span> Example comparison</header>
<div class="article-table-content-wrapper" tabindex="0">
<table class="table article-section__table">
<tbody>
<tr>
<td>RAD</td>
<td>1</td>
</tr>
</tbody>
</table>
</div>
<div class="article-section__table-footnotes">
<ul>
<li>n: no; y: yes.</li>
</ul>
</div>
</div>
<p>As a result, confusion may arise as to which protocol is appropriate.</p>
</section>
</main>
</body>
</html>
"""


WILEY_NESTED_BODY_HTML = """
<html>
  <body>
    <div class="article__sections">
      <section class="article-section" data-section-type="body">
        <div class="article-section__content" id="section-2">
          <h2 class="article-section__title section__title">Methods</h2>
          <p>Sequencing libraries were prepared using a custom protocol.</p>
          <section class="article-section__content--sub" id="section-2-1">
            <h3 class="article-section__title section__subtitle">Sampling</h3>
            <p>We sampled ten locations spanning the native range.</p>
          </section>
        </div>
      </section>
    </div>
  </body>
</html>
"""


WILEY_COMPLEX_BODY_HTML = """
<html>
  <body>
    <div id="pb-page-content">
      <section class="article-section article-section__full">
        <section class="article-section__content" id="men12273-sec-0001">
          <h2 class="article-section__title section__title section1" id="men12273-sec-0001-title"> Introduction</h2>
          <p>Application of post-Sanger sequencing technologies in the field of ecology has accelerated since the introduction of Restriction site Associated DNA sequencing (RADseq; Baird <i>et&nbsp;al.</i> <a href="#men12273-bib-0002">2008</a>).</p>
          <div class="article-table-content" id="men12273-tbl-0001">
            <header class="article-table-caption"><span class="table-caption__label">Table 1.</span> Comparison of approaches used to reduce the number of loci targeted in common genotyping by sequencing methods</header>
            <div class="article-table-content-wrapper" tabindex="0">
              <table class="table article-section__table">
                <tbody>
                  <tr><td>RAD</td><td>1</td></tr>
                </tbody>
              </table>
            </div>
            <div class="article-section__table-footnotes">
              <ul><li>n: no; y: yes.</li></ul>
            </div>
          </div>
          <p>As a result, confusion may arise as to which of the available protocols may be most appropriate for a given experimental design.</p>
        </section>
      </section>
      <section class="article-section article-section__full">
        <section class="article-section__content" id="men12273-sec-0002">
          <h2 class="article-section__title section__title section1" id="men12273-sec-0002-title"> SimRAD workflow and functions</h2>
          <p>A subsample or the full reference genome sequence of a species can be used to simulate restriction enzyme digestion.</p>
          <section class="article-section__inline-figure">
            <figure class="figure" id="men12273-fig-0001">
              <figcaption class="figure__caption">
                <div class="figure__caption__header"><strong class="figure__title">Figure 1</strong></div>
                <div class="figure__caption-text">SimRAD workflow overview.</div>
              </figcaption>
            </figure>
          </section>
          <section class="article-section__sub-content" id="men12273-sec-0003">
            <h3 class="article-section__sub-title section2" id="men12273-sec-0003-title"> Data input</h3>
            <p>When reference sequences for a species are available the function <i>ref.DNAseq</i> can be used to load sequences contained in a FASTA file.</p>
            <div class="article-table-content" id="men12273-tbl-0002">
              <header class="article-table-caption"><span class="table-caption__label">Table 2.</span> Comparison of the number of loci predicted using SimRAD and reported in the literature.</header>
            </div>
          </section>
        </section>
      </section>
    </div>
  </body>
</html>
"""


WILEY_ACCORDION_BODY_HTML = """
<html>
  <body>
    <div class="accordion" id="article-sections">
      <div class="accordion__panel" data-test-locator="article-section">
        <div class="accordion__panel-body" data-test-locator="article-section-content" id="sec-1">
          <h2 class="section__title">Introduction</h2>
          <p>The introductory panel content describes the scope of the study.</p>
        </div>
      </div>
      <div class="accordion__panel" data-testid="article-section">
        <div class="accordion__panel-body" id="sec-2" aria-labelledby="sec-2-title">
          <h2 class="section__title" id="sec-2-title">Results</h2>
          <p>The results panel summarises the main findings.</p>
        </div>
      </div>
    </div>
  </body>
</html>
"""


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



def test_wiley_parser_extracts_body_sections() -> None:
    url = "https://onlinelibrary.wiley.com/doi/10.1002/example"
    parsed = parse_html(url, WILEY_BODY_HTML)
    body = parsed.content_sections["body"]
    assert body
    first = body[0]
    assert first["title"].strip() == "Introduction"
    paragraphs = first.get("paragraphs") or []
    assert any(
        paragraph.get("markdown", "").startswith("Application of post-Sanger sequencing technologies")
        for paragraph in paragraphs
    )
    assert any(
        "Table 1." in paragraph.get("markdown", "")
        for paragraph in paragraphs
    )


def test_wiley_parser_handles_nested_section_wrappers() -> None:
    url = "https://onlinelibrary.wiley.com/doi/10.1002/example"
    parsed = parse_html(url, WILEY_NESTED_BODY_HTML)
    body = parsed.content_sections["body"]
    assert body
    first = body[0]
    assert first["title"].strip() == "Methods"
    paragraphs = first.get("paragraphs") or []
    assert any(
        paragraph.get("markdown", "").startswith("Sequencing libraries were prepared")
        for paragraph in paragraphs
    )
    children = first.get("children") or []
    assert children
    child = children[0]
    assert child["title"].strip() == "Sampling"
    child_paragraphs = child.get("paragraphs") or []
    assert any(
        "sampled ten locations" in paragraph.get("markdown", "")
        for paragraph in child_paragraphs
    )


def test_wiley_parser_handles_complex_full_sections() -> None:
    url = "https://onlinelibrary.wiley.com/doi/10.1111/1755-0998.12273"
    parsed = parse_html(url, WILEY_COMPLEX_BODY_HTML)
    body = parsed.content_sections["body"]
    assert body
    titles = [section.get("title", "").strip() for section in body]
    assert "Introduction" in titles
    assert "SimRAD workflow and functions" in titles

    introduction = next(section for section in body if section.get("title", "").strip() == "Introduction")
    intro_paragraphs = introduction.get("paragraphs") or []
    assert any(
        "Application of post-Sanger sequencing technologies" in paragraph.get("markdown", "")
        for paragraph in intro_paragraphs
    )
    assert any(
        "Table 1." in paragraph.get("markdown", "")
        for paragraph in intro_paragraphs
    )

    workflow = next(section for section in body if section.get("title", "").strip() == "SimRAD workflow and functions")
    workflow_paragraphs = workflow.get("paragraphs") or []
    assert any(
        "full reference genome sequence" in paragraph.get("markdown", "")
        for paragraph in workflow_paragraphs
    )
    children = workflow.get("children") or []
    assert children
    data_input = next(child for child in children if child.get("title", "").strip() == "Data input")
    child_paragraphs = data_input.get("paragraphs") or []
    assert any("ref.DNAseq" in paragraph.get("markdown", "") for paragraph in child_paragraphs)


def test_wiley_parser_handles_accordion_panels() -> None:
    url = "https://onlinelibrary.wiley.com/doi/10.1002/example"
    parsed = parse_html(url, WILEY_ACCORDION_BODY_HTML)
    body = parsed.content_sections["body"]
    assert body
    titles = {section.get("title", "").strip() for section in body}
    assert {"Introduction", "Results"}.issubset(titles)

    intro = next(section for section in body if section.get("title", "").strip() == "Introduction")
    intro_paragraphs = intro.get("paragraphs") or []
    assert any(
        "introductory panel content" in paragraph.get("markdown", "")
        for paragraph in intro_paragraphs
    )

    results = next(section for section in body if section.get("title", "").strip() == "Results")
    results_paragraphs = results.get("paragraphs") or []
    assert any(
        "summarises the main findings" in paragraph.get("markdown", "")
        for paragraph in results_paragraphs
    )

