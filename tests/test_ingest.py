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


DOM_FOR_POST_NO_DOI = """<!doctype html>
<html>
  <head>
    <title>Title Tag</title>
    <meta name="citation_title" content="Server-Side Title">
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
            "meta": {"title": "Client Title"},
            "content_html": CONTENT_FOR_POST,
            "references": [],
        },
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    resp = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
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


def test_dedupe_by_canonical_url_hash_returns_same_capture_id_when_no_doi(client):
    payload = {
        "source_url": "https://example.org/post?utm_source=x#frag",
        "dom_html": DOM_FOR_POST_NO_DOI,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r1 = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    r2 = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r1.status_code in (200, 201)
    assert r2.status_code in (200, 201)

    id1 = r1.get_json()["capture_id"]
    id2 = r2.get_json()["capture_id"]
    assert id1 == id2


def test_dedupe_by_doi_returns_same_capture_id_for_different_urls(client):
    payload1 = {
        "source_url": "https://example.org/post?utm_source=x#frag",
        "dom_html": DOM_FOR_POST,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }
    payload2 = {
        "source_url": "https://publisher.example.com/articles/abc123?ref=whatever",
        "dom_html": DOM_FOR_POST,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r1 = client.post(
        "/api/captures/", data=json.dumps(payload1), content_type="application/json"
    )
    r2 = client.post(
        "/api/captures/", data=json.dumps(payload2), content_type="application/json"
    )
    assert r1.status_code in (200, 201)
    assert r2.status_code in (200, 201)

    id1 = r1.get_json()["capture_id"]
    id2 = r2.get_json()["capture_id"]
    assert id1 == id2


def test_ingest_missing_source_url_is_400(client):
    payload = {"dom_html": "<html></html>"}
    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code == 400
    j = r.get_json()
    assert j["error"]["code"] == "missing_field"
    assert j["error"]["details"]["field"] == "source_url"


def test_ingest_weird_extraction_types_still_ingests(client):
    payload = {
        "source_url": "https://example.org/weird",
        "dom_html": DOM_FOR_POST,
        "extraction": "nope",  # should be coerced to {}
        "client": {"ext": "chrome", "v": "0.1.0"},
    }
    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    assert r.get_json()["capture_id"]


def test_parser_exception_still_saves_capture_and_persists_parse_error_summary(
    client, monkeypatch
):
    import paperclip.ingest_parse as ingest_parse

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(ingest_parse, "parse_article", boom)

    payload = {
        "source_url": "https://example.org/crash",
        "dom_html": DOM_FOR_POST,
        "extraction": {"meta": {"citation_title": "X"}},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }

    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    cap_id = r.get_json()["capture_id"]

    r2 = client.get(f"/api/captures/{cap_id}/")
    assert r2.status_code == 200
    row = r2.get_json()

    meta = json.loads(row["meta_json"])
    assert "_parse" in meta
    assert meta["_parse"]["parser"] == "crashed"
    assert meta["_parse"]["ok"] is False
    assert isinstance(meta["_parse"].get("error"), dict)
    assert meta["_parse"]["error"]["type"] == "RuntimeError"
