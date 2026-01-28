from __future__ import annotations

import json

DOM_WITH_ACKS = """<!doctype html>
<html>
  <head>
    <title>Papers JSONL Test</title>
    <meta name="citation_title" content="Papers JSONL Test">
    <meta name="citation_doi" content="10.1234/papers.jsonl.test">
    <meta name="prism.publicationdate" content="2022-01-02">
    <meta name="citation_journal_title" content="Journal of Papers">
  </head>
  <body>
    <article>
      <h2>Introduction</h2>
      <p>This is the intro paragraph.</p>

      <h2>Acknowledgements</h2>
      <p>Thanks to everyone.</p>

      <h2>Funding</h2>
      <p>Funded by X.</p>

      <h2>Conflicts of Interest</h2>
      <p>No conflicts declared.</p>

      <h2>References</h2>
      <ol>
        <li>Ref A. 2020. Some Paper.</li>
      </ol>
    </article>
  </body>
</html>
"""

CONTENT_FOR_POST = "<div><p>Fallback content.</p></div>"


def _post_capture(client) -> str:
    payload = {
        "source_url": "https://example.org/papers-jsonl",
        "dom_html": DOM_WITH_ACKS,
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }
    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    return r.get_json()["capture_id"]


def _parse_ndjson(body: str) -> list[dict]:
    lines = [ln for ln in (body or "").splitlines() if ln.strip()]
    out = []
    for ln in lines:
        out.append(json.loads(ln))
    return out


def test_export_papers_jsonl_excludes_noise_kinds_and_includes_sections(client):
    cap_id = _post_capture(client)

    out = client.get("/exports/papers.jsonl/")
    assert out.status_code == 200
    body = out.get_data(as_text=True)

    rows = _parse_ndjson(body)
    row = next((x for x in rows if x.get("id") == cap_id), None)
    assert row is not None
    assert row["doi"] == "10.1234/papers.jsonl.test"

    # NEW: stable provenance fields
    assert isinstance(row.get("captured_at"), str)
    assert row["captured_at"].strip() != ""
    assert row.get("published_date_raw") == "2022-01-02"

    # NEW: parse provenance fields exist
    assert isinstance(row.get("parse_parser"), str)
    assert isinstance(row.get("parse_ok"), bool)
    assert isinstance(row.get("capture_quality"), str)
    assert isinstance(row.get("blocked_reason"), str)
    assert isinstance(row.get("confidence_fulltext"), (int, float))
    assert isinstance(row.get("used_for_index"), bool)

    secs = row.get("sections")
    assert isinstance(secs, list)

    # Should include intro
    assert any(s.get("kind") == "introduction" for s in secs)

    # Should exclude these kinds from papers.jsonl
    assert not any(s.get("kind") == "acknowledgements" for s in secs)
    assert not any(s.get("kind") == "funding" for s in secs)
    assert not any(s.get("kind") == "conflicts" for s in secs)


def test_export_selected_papers_jsonl_only_includes_selected(client):
    id1 = _post_capture(client)

    # second capture with different DOI
    payload2 = {
        "source_url": "https://example.org/papers-jsonl-2",
        "dom_html": DOM_WITH_ACKS.replace(
            "10.1234/papers.jsonl.test", "10.9999/papers.jsonl.other"
        ).replace("Papers JSONL Test", "Papers JSONL Test 2"),
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }
    r2 = client.post(
        "/api/captures/", data=json.dumps(payload2), content_type="application/json"
    )
    assert r2.status_code in (200, 201)
    id2 = r2.get_json()["capture_id"]
    assert id1 != id2

    out = client.post(
        "/exports/papers.jsonl/selected/",
        data={"capture_ids": [id1]},
        follow_redirects=False,
    )
    assert out.status_code == 200
    body = out.get_data(as_text=True)

    rows = _parse_ndjson(body)
    assert any(x.get("id") == id1 for x in rows)
    assert not any(x.get("id") == id2 for x in rows)
