from __future__ import annotations

import json

import pytest


def test_search_finds_content_only_via_fts_when_enabled(client, app):
    # If FTS isn't available in this environment, this test isn't meaningful.
    if not bool(app.config.get("FTS_ENABLED")):
        pytest.skip("FTS not enabled in this SQLite build")

    token = "zebracorn"
    payload = {
        "source_url": "https://example.org/fts-content-only",
        "dom_html": """<!doctype html>
<html>
  <head>
    <title>Completely Unrelated Title</title>
    <meta name="citation_title" content="Completely Unrelated Title">
    <meta name="citation_doi" content="10.9099/fts.test">
    <meta name="prism.publicationdate" content="2020-11-02">
    <meta name="citation_journal_title" content="Journal of FTS">
  </head>
  <body><article><p>Nothing to see.</p></article></body>
</html>
""",
        # Token appears ONLY in content_html -> content_text.
        "extraction": {
            "meta": {},
            "content_html": f"<div><p>This content contains {token} and should be searchable.</p></div>",
            "references": [],
        },
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)

    # With FTS enabled, library search path uses capture_fts for content_text
    s = client.get(f"/api/library/?q={token}")
    assert s.status_code == 200
    d = s.get_json()
    assert d["total"] >= 1
    assert any(token not in (c.get("title") or "") for c in d["captures"])
