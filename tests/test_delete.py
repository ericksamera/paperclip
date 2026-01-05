from __future__ import annotations

import json
from pathlib import Path


DOM_FOR_POST = """<!doctype html>
<html>
  <head>
    <title>Title Tag</title>
    <meta name="citation_title" content="Server-Side Title">
    <meta name="citation_doi" content="10.9999/xyz.abc">
    <meta name="prism.publicationdate" content="2020-11-02">
    <meta name="citation_journal_title" content="Journal of Testing">
    <meta name="citation_keywords" content="alpha, beta; gamma">
  </head>
  <body><article><p>Hello A.</p><p>Hello B.</p></article></body>
</html>
"""

CONTENT_FOR_POST = "<div><p>Hello A.</p><p>Hello B.</p></div>"


def test_delete_selected_captures_removes_db_rows_and_artifacts(client, app):
    payload = {
        "source_url": "https://example.org/post?utm_source=x#frag",
        "dom_html": DOM_FOR_POST,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    cap_id = r.get_json()["capture_id"]

    arts = Path(app.config["ARTIFACTS_DIR"]) / cap_id
    assert arts.exists()

    # Sanity: capture is fetchable
    g1 = client.get(f"/api/captures/{cap_id}/")
    assert g1.status_code == 200

    d = client.post(
        "/captures/delete/",
        data={"capture_ids": [cap_id], "next": "/library/"},
        follow_redirects=False,
    )
    assert d.status_code in (302, 303)

    # Gone from DB
    g2 = client.get(f"/api/captures/{cap_id}/")
    assert g2.status_code == 404

    # Artifacts removed
    assert not arts.exists()
