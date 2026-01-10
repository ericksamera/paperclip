from __future__ import annotations

import json
from pathlib import Path

from paperclip.db import get_db


def _dom_with_doi(doi: str) -> str:
    return f"""<!doctype html>
<html>
  <head>
    <title>Title Tag</title>
    <meta name="citation_title" content="Server-Side Title">
    <meta name="citation_doi" content="{doi}">
    <meta name="prism.publicationdate" content="2020-11-02">
    <meta name="citation_journal_title" content="Journal of Validation">
  </head>
  <body><article><p>Hello A.</p><p>Hello B.</p></article></body>
</html>
"""


CONTENT_FOR_POST = "<div><p>Hello A.</p><p>Hello B.</p></div>"


def _post_capture(client, source_url: str, doi: str) -> str:
    payload = {
        "source_url": source_url,
        "dom_html": _dom_with_doi(doi),
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }
    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    return r.get_json()["capture_id"]


def test_bulk_add_requires_capture_ids_and_valid_collection_id(client, app):
    cap_id = _post_capture(client, "https://example.org/val", "10.9090/val")

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO collections (name, created_at) VALUES (?, datetime('now'))",
            ("Validation Collection",),
        )
        db.commit()
        col_id = db.execute(
            "SELECT id FROM collections WHERE name = ?",
            ("Validation Collection",),
        ).fetchone()["id"]

        before = db.execute("SELECT COUNT(1) AS n FROM collection_items").fetchone()[
            "n"
        ]

    # Missing capture_ids => redirect, no DB change
    r1 = client.post(
        "/captures/collections/add/",
        data={"collection_id": str(col_id), "next": "/library/"},
        follow_redirects=False,
    )
    assert r1.status_code in (302, 303)

    with app.app_context():
        db = get_db()
        after1 = db.execute("SELECT COUNT(1) AS n FROM collection_items").fetchone()[
            "n"
        ]
    assert after1 == before

    # Invalid collection_id => redirect, no DB change
    r2 = client.post(
        "/captures/collections/add/",
        data={"capture_ids": [cap_id], "collection_id": "0", "next": "/library/"},
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303)

    with app.app_context():
        db = get_db()
        after2 = db.execute("SELECT COUNT(1) AS n FROM collection_items").fetchone()[
            "n"
        ]
    assert after2 == before


def test_export_selected_requires_ids(client):
    r1 = client.post(
        "/exports/bibtex/selected/",
        data={},
        follow_redirects=False,
    )
    assert r1.status_code in (302, 303)

    r2 = client.post(
        "/exports/ris/selected/",
        data={},
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303)


def test_delete_with_no_ids_redirects_and_mixed_ids_is_safe(client, app):
    cap_id = _post_capture(client, "https://example.org/del", "10.1010/del")

    # No ids => redirect
    r0 = client.post(
        "/captures/delete/", data={"next": "/library/"}, follow_redirects=False
    )
    assert r0.status_code in (302, 303)

    # Mixed valid + bogus => should still succeed and remove valid
    arts = Path(app.config["ARTIFACTS_DIR"]) / cap_id
    assert arts.exists()

    r = client.post(
        "/captures/delete/",
        data={"capture_ids": [cap_id, "not-a-real-id"], "next": "/library/"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    # Gone from DB
    g = client.get(f"/api/captures/{cap_id}/")
    assert g.status_code == 404

    # Artifacts removed for the real one (bogus one is fine)
    assert not arts.exists()
