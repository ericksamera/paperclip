from __future__ import annotations

import json

import pytest


def _post_capture_with_token(client, *, token: str) -> str:
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
    d = r.get_json()
    assert isinstance(d, dict)
    assert isinstance(d.get("capture_id"), str)
    return d["capture_id"]


def test_search_finds_content_only_via_fts_when_enabled(client, app):
    if not bool(app.config.get("FTS_ENABLED")):
        pytest.skip("FTS not enabled in this SQLite build")

    token = "zebracorn"
    _post_capture_with_token(client, token=token)

    s = client.get(f"/api/library/?q={token}")
    assert s.status_code == 200
    d = s.get_json()
    assert d["total"] >= 1


def test_rebuild_fts_repairs_missing_rows(client, app):
    if not bool(app.config.get("FTS_ENABLED")):
        pytest.skip("FTS not enabled in this SQLite build")

    token = "otterquartz"
    cap_id = _post_capture_with_token(client, token=token)

    # Confirm searchable
    s1 = client.get(f"/api/library/?q={token}")
    assert s1.status_code == 200
    assert s1.get_json()["total"] >= 1

    # Delete its FTS row directly (simulate corruption / missed update)
    with app.app_context():
        from paperclip.db import get_db

        db = get_db()
        rid_row = db.execute(
            "SELECT rowid AS rid FROM captures WHERE id = ? LIMIT 1", (cap_id,)
        ).fetchone()
        assert rid_row and rid_row["rid"] is not None
        rid = int(rid_row["rid"])

        db.execute("DELETE FROM capture_fts WHERE rowid = ?", (rid,))
        db.commit()

    # Now the token should NOT be found
    s2 = client.get(f"/api/library/?q={token}")
    assert s2.status_code == 200
    assert s2.get_json()["total"] == 0

    # Rebuild
    r = client.post("/api/maintenance/rebuild-fts/")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["stats"]["fts_rows"] >= 1

    # Search works again
    s3 = client.get(f"/api/library/?q={token}")
    assert s3.status_code == 200
    assert s3.get_json()["total"] >= 1


def test_verify_fts_detects_mismatch_and_can_repair(client, app):
    if not bool(app.config.get("FTS_ENABLED")):
        pytest.skip("FTS not enabled in this SQLite build")

    token = "marmotnebula"
    cap_id = _post_capture_with_token(client, token=token)

    # Healthcheck should be OK initially
    v1 = client.get("/api/maintenance/verify-fts/")
    assert v1.status_code == 200
    d1 = v1.get_json()
    assert d1["ok"] is True
    assert d1["repaired"] is False

    # Break one row
    with app.app_context():
        from paperclip.db import get_db

        db = get_db()
        rid_row = db.execute(
            "SELECT rowid AS rid FROM captures WHERE id = ? LIMIT 1", (cap_id,)
        ).fetchone()
        assert rid_row and rid_row["rid"] is not None
        rid = int(rid_row["rid"])
        db.execute("DELETE FROM capture_fts WHERE rowid = ?", (rid,))
        db.commit()

    # Healthcheck should now report mismatch
    v2 = client.get("/api/maintenance/verify-fts/")
    assert v2.status_code == 200
    d2 = v2.get_json()
    assert d2["ok"] is False
    assert d2["stats"]["missing_rows"] >= 1

    # One-click repair
    v3 = client.get("/api/maintenance/verify-fts/?repair=1")
    assert v3.status_code == 200
    d3 = v3.get_json()
    assert d3["repaired"] is True
    assert d3["ok"] is True

    # Search works again
    s = client.get(f"/api/library/?q={token}")
    assert s.status_code == 200
    assert s.get_json()["total"] >= 1
