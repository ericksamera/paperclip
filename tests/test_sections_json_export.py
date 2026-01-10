from __future__ import annotations

import json
from pathlib import Path


DOM_WITH_REFERENCES = """<!doctype html>
<html>
  <head>
    <title>Sections JSON Test</title>
    <meta name="citation_title" content="Sections JSON Test">
    <meta name="citation_doi" content="10.1234/sections.json.test">
    <meta name="prism.publicationdate" content="2022-01-02">
    <meta name="citation_journal_title" content="Journal of Sections">
  </head>
  <body>
    <article>
      <h2>Introduction</h2>
      <p>This is the intro paragraph.</p>

      <h2>Methods</h2>
      <p>This is the methods paragraph.</p>

      <h2>References</h2>
      <ol>
        <li>Ref A. 2020. Some Paper.</li>
      </ol>
    </article>
  </body>
</html>
"""

CONTENT_FOR_POST = "<div><p>Fallback content.</p></div>"


def test_export_sections_json_includes_sections(client, app):
    payload = {
        "source_url": "https://example.org/sections-json",
        "dom_html": DOM_WITH_REFERENCES,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    cap_id = r.get_json()["capture_id"]

    # sanity: sections.json artifact exists
    cap_dir = Path(app.config["ARTIFACTS_DIR"]) / cap_id
    assert (cap_dir / "sections.json").exists()

    out = client.get("/exports/sections.json/")
    assert out.status_code == 200
    body = out.get_data(as_text=True)

    data = json.loads(body)
    assert isinstance(data, list)
    row = next((x for x in data if x.get("id") == cap_id), None)
    assert row is not None
    assert row["doi"] == "10.1234/sections.json.test"

    secs = row.get("sections")
    assert isinstance(secs, list)
    assert any(s.get("kind") == "introduction" for s in secs)
    assert any(s.get("kind") == "methods" for s in secs)
    # references should not be sectionized (they're split out)
    assert not any(s.get("kind") == "references" for s in secs)
