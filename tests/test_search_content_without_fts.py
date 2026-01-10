from __future__ import annotations

import json


def _post_capture_with_token(client, *, token: str) -> str:
    payload = {
        "source_url": "https://example.org/nofts",
        "dom_html": """<!doctype html>
<html>
  <head>
    <title>No-FTS Title</title>
    <meta name="citation_title" content="No-FTS Title">
    <meta name="citation_doi" content="10.9099/nofts.test">
    <meta name="prism.publicationdate" content="2020-11-02">
    <meta name="citation_journal_title" content="Journal of No FTS">
  </head>
  <body><article><p>Nothing to see.</p></article></body>
</html>
""",
        "extraction": {
            "meta": {},
            "content_html": f"<div><p>This blob contains {token} but not in title/doi.</p></div>",
            "references": [],
        },
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    j = r.get_json()
    assert isinstance(j, dict) and isinstance(j.get("capture_id"), str)
    return j["capture_id"]


def test_search_finds_content_via_capture_text_when_fts_disabled(client, app):
    # Force routes to take the non-FTS query path.
    app.config["FTS_ENABLED"] = False

    token = "platypus_sapphire_123"
    _post_capture_with_token(client, token=token)

    r = client.get(f"/api/library/?q={token}")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, dict)
    assert data["total"] >= 1
