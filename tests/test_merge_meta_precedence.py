from __future__ import annotations

import json
from pathlib import Path


def test_client_meta_overrides_head_meta_on_same_key(client, app):
    dom_html = """<!doctype html>
<html>
  <head>
    <title>Head Title</title>
    <meta name="citation_title" content="Head Citation Title">
    <meta name="citation_doi" content="10.1234/merge.meta">
    <meta name="citation_journal_title" content="Head Journal">
  </head>
  <body><article><p>Hi.</p></article></body>
</html>
"""

    payload = {
        "source_url": "https://example.org/merge-meta",
        "dom_html": dom_html,
        "extraction": {
            "meta": {
                "citation_title": "Client Citation Title",
                "citation_journal_title": "Client Journal",
            },
            "content_html": "<div><p>Hi.</p></div>",
            "references": [],
        },
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    cap_id = r.get_json()["capture_id"]

    cap_dir = Path(app.config["ARTIFACTS_DIR"]) / cap_id
    reduced = json.loads((cap_dir / "reduced.json").read_text(encoding="utf-8"))

    # Title selection prefers head meta citation_title, but merge_meta should store the merged head meta
    # (and for collisions, client meta should win inside reduced["meta"]).
    assert reduced["doi"] == "10.1234/merge.meta"
    assert reduced["meta"]["citation_title"] == "Client Citation Title"
    assert reduced["meta"]["citation_journal_title"] == "Client Journal"
