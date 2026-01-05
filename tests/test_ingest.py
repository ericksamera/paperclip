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


def test_post_capture_writes_artifacts_and_extracts_fields(client, app):
    payload = {
        "source_url": "https://example.org/post?utm_source=x#frag",
        "dom_html": DOM_FOR_POST,
        "extraction": {
            "meta": {
                "title": "Client Title"
            },
            "content_html": CONTENT_FOR_POST,
            "references": [],
        },
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    resp = client.post("/api/captures/", data=json.dumps(payload), content_type="application/json")
    assert resp.status_code in (200, 201)
    data = resp.get_json()
    assert data and data.get("capture_id")
    cap_id = data["capture_id"]

    # Artifacts exist
    arts = Path(app.config["ARTIFACTS_DIR"]) / cap_id
    assert (arts / "page.html").exists()
    assert (arts / "content.html").exists()
    assert (arts / "raw.json").exists()
    assert (arts / "reduced.json").exists()

    reduced = json.loads((arts / "reduced.json").read_text(encoding="utf-8"))
    assert reduced["title"] == "Server-Side Title"
    assert reduced["doi"] == "10.9999/xyz.abc"
    assert reduced["year"] == 2020
    assert reduced["container_title"] == "Journal of Testing"
    assert reduced["keywords"] == ["alpha", "beta", "gamma"]


def test_dedupe_by_canonical_url_hash_returns_same_capture_id(client):
    payload = {
        "source_url": "https://example.org/post?utm_source=x#frag",
        "dom_html": DOM_FOR_POST,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r1 = client.post("/api/captures/", data=json.dumps(payload), content_type="application/json")
    r2 = client.post("/api/captures/", data=json.dumps(payload), content_type="application/json")
    assert r1.status_code in (200, 201)
    assert r2.status_code in (200, 201)

    id1 = r1.get_json()["capture_id"]
    id2 = r2.get_json()["capture_id"]
    assert id1 == id2
