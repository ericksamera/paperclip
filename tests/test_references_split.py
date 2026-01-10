from __future__ import annotations

import json
from pathlib import Path


DOM_WITH_REFERENCES = """<!doctype html>
<html>
  <head>
    <title>Split Test</title>
    <meta name="citation_title" content="Split Test">
    <meta name="citation_doi" content="10.1234/split.test">
    <meta name="prism.publicationdate" content="2022-01-02">
    <meta name="citation_journal_title" content="Journal of Splits">
  </head>
  <body>
    <article>
      <h2>Introduction</h2>
      <p>This is the body paragraph.</p>

      <h2>References</h2>
      <ol>
        <li>Ref A. 2020. Some Paper.</li>
        <li>Ref B. 2021. Another Paper.</li>
      </ol>
    </article>
  </body>
</html>
"""

CONTENT_FOR_POST = "<div><p>This is the body paragraph.</p></div>"


def test_ingest_writes_references_artifacts_and_splits_text(client, app):
    payload = {
        "source_url": "https://example.org/split",
        "dom_html": DOM_WITH_REFERENCES,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r = client.post(
        "/api/captures/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert r.status_code in (200, 201)
    cap_id = r.get_json()["capture_id"]

    cap_dir = Path(app.config["ARTIFACTS_DIR"]) / cap_id
    assert cap_dir.exists()

    # Article should be body-only (no references section)
    article_txt = (cap_dir / "article.txt").read_text(encoding="utf-8")
    assert "Introduction" in article_txt
    assert "This is the body paragraph." in article_txt
    assert "References" not in article_txt
    assert "Ref A" not in article_txt

    # References should include the heading + list items
    refs_txt = (cap_dir / "references.txt").read_text(encoding="utf-8")
    assert "References" in refs_txt
    assert "Ref A" in refs_txt
    assert "Ref B" in refs_txt

    # article.json should include references_* fields (even if empty on some pages)
    article_json = json.loads((cap_dir / "article.json").read_text(encoding="utf-8"))
    assert "references_text" in article_json
    assert "references_html" in article_json

    # NEW: sectionizer meta should exist and should NOT include the references section
    meta = article_json.get("meta") or {}
    assert isinstance(meta, dict)
    assert meta.get("sections_count", 0) >= 1
    sections = meta.get("sections") or []
    assert isinstance(sections, list)
    # We should have an introduction-like section in the body
    assert any((s.get("kind") == "introduction") for s in sections)
    # And we should not see References heading as a section in article_text (it was split out)
    assert not any((s.get("kind") == "references") for s in sections)


def test_capture_detail_page_renders_with_parsed_context(client, app):
    payload = {
        "source_url": "https://example.org/split2",
        "dom_html": DOM_WITH_REFERENCES,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r = client.post(
        "/api/captures/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert r.status_code in (200, 201)
    cap_id = r.get_json()["capture_id"]

    page = client.get(f"/captures/{cap_id}/")
    assert page.status_code == 200
    body = page.get_data(as_text=True)

    # Quick sanity checks that the parsed panel is present
    assert "Parsed text" in body
    assert "Article body" in body
    assert "References" in body
