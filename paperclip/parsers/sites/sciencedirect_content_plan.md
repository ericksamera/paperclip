# ScienceDirect article body parsing plan

## Goal
Extend `ScienceDirectParser` so it captures the full body content (introduction, methods, results, etc.) from ScienceDirect article pages in a structured way that is consistent with the rest of the parser pipeline.

## Observed markup
- Article body sections live under `<section id="cesec…">` blocks. Each block contains a heading (`<h2>` with classes like `u-h4`) followed by one or more content containers (`<div class="u-margin-s-bottom" …>`). The example snippet below shows the `CONCLUSIONS` section:
  ```html
  <section id="cesec150">
    <h2 class="u-h4 …">CONCLUSIONS</h2>
    <div class="u-margin-s-bottom" id="para460">…</div>
  </section>
  ```
- The body container for a page typically looks like `<section class="Abstracts" …>` followed by `<section class="Sections" …>`; each numbered `cesec` section corresponds to a visible heading in the article.
- Paragraph text is wrapped in `div` elements rather than `<p>` tags (ScienceDirect uses spans and nested inline tags inside those divs).
- Some sections contain subheadings (e.g., `<h3>` or `<h4>` inside the same `section` block) or nested `<section>` children for subsections.
- Non-body sections we must ignore while iterating: graphical abstracts/highlights, references, author info blocks, footnotes, etc.

## Proposed extraction steps
1. **Locate the article body root.**
   - Select the container that holds the main sections (e.g., `section[id^='body']` or `section.article-body`).
   - If not found, fall back to scanning the entire document for `section[id^='cesec']` to keep the parser resilient.
2. **Iterate main sections.**
   - For each top-level `section[id^='cesec']` that is a direct child of the body container:
     - Extract the heading text from the first `<h2>` or fallback to `<h3>/<h4>`.
     - Collect the sibling content nodes until the next top-level section. Accept both `<div>` paragraphs and nested section blocks.
     - Normalize whitespace and preserve inline HTML (italics, math, links) for downstream rendering.
3. **Handle subsections.**
   - If we encounter nested `<section>` elements (`<section id="cesec150s0005">` style ids), treat them as subsections. Represent them as nested structures: `{"title": "Subheading", "html": "…"}` under the parent section’s `children` list.
   - Ensure we keep the DOM order intact, including alternating paragraphs and subheadings.
4. **Clean and normalize content.**
   - Remove editorial artifacts (e.g., `data-locator` anchors, `span` wrappers used for styling) while preserving semantic tags (`<em>`, `<strong>`, `<a>`).
   - Convert repeated `<div>` wrappers into `<p>` tags or at least ensure line breaks when serializing.
   - Strip leading/trailing whitespace but avoid collapsing purposeful line breaks.
5. **Populate `content_sections`.**
   - Add a new key (e.g., `"body"`) whose value is an ordered list of dictionaries: `[{"title": "CONCLUSIONS", "markdown": "…", "paragraphs": [...]}, …]`.
   - Each paragraph entry should expose Markdown text plus a sentence-level breakdown with associated citation ids so downstream consumers can target specific statements.
   - When headings are missing, fall back to sequential numbering (`Section 1`, `Section 2`, …) so the client can still render the text.
   - Preserve the existing abstract/keyword behavior in `_build_content_sections` and append the body sections after them.
6. **Testing strategy.**
   - Create fixture HTML snippets that cover:
     - Plain paragraphs within a section (like the CONCLUSIONS example).
     - Sections containing nested subsections/subheadings.
     - Pages with proxy-modified hosts to ensure detection still works.
   - Add unit tests validating that `content_sections["body"]` contains the expected titles and HTML, and that abstract/keywords remain untouched.

## Open questions / follow-ups
- Verify whether tables/figures embedded within sections need additional handling (e.g., capture them separately or leave inside the section HTML).
- Confirm whether we should expose a flat Markdown string in addition to the structured HTML for compatibility with the rest of the app.
- Investigate if ScienceDirect ever omits the `cesec` id pattern; if so, expand selectors accordingly.
