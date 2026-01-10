from __future__ import annotations

import json

from paperclip.db import get_db


def _dom_with_doi(doi: str) -> str:
    return f"""<!doctype html>
<html>
  <head>
    <title>Title Tag</title>
    <meta name="citation_title" content="Server-Side Title">
    <meta name="citation_doi" content="{doi}">
    <meta name="prism.publicationdate" content="2020-11-02">
    <meta name="citation_journal_title" content="Journal of Testing">
    <meta name="citation_keywords" content="alpha, beta; gamma">
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


def test_bulk_add_remove_and_export_selected(client, app):
    id1 = _post_capture(client, "https://example.org/a", "10.1111/aaa")
    id2 = _post_capture(client, "https://example.org/b", "10.2222/bbb")

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO collections (name, created_at) VALUES (?, datetime('now'))",
            ("My Collection",),
        )
        db.commit()
        col_id = db.execute(
            "SELECT id FROM collections WHERE name = ?",
            ("My Collection",),
        ).fetchone()["id"]

    # Add both to collection
    r_add = client.post(
        "/captures/collections/add/",
        data={
            "capture_ids": [id1, id2],
            "collection_id": str(col_id),
            "next": "/library/",
        },
        follow_redirects=False,
    )
    assert r_add.status_code in (302, 303)

    with app.app_context():
        db = get_db()
        rows = db.execute(
            "SELECT capture_id FROM collection_items WHERE collection_id = ?",
            (col_id,),
        ).fetchall()
        assert {r["capture_id"] for r in rows} == {id1, id2}

    # Remove one
    r_rm = client.post(
        "/captures/collections/remove/",
        data={"capture_ids": [id2], "collection_id": str(col_id), "next": "/library/"},
        follow_redirects=False,
    )
    assert r_rm.status_code in (302, 303)

    with app.app_context():
        db = get_db()
        rows = db.execute(
            "SELECT capture_id FROM collection_items WHERE collection_id = ?",
            (col_id,),
        ).fetchall()
        assert {r["capture_id"] for r in rows} == {id1}

    # Export selected (BibTeX)
    bib = client.post(
        "/exports/bibtex/selected/",
        data={"capture_ids": [id1]},
        follow_redirects=False,
    )
    assert bib.status_code == 200
    body = bib.get_data(as_text=True)
    assert "10.1111/aaa" in body
    assert "10.2222/bbb" not in body

    # Export selected (RIS)
    ris = client.post(
        "/exports/ris/selected/",
        data={"capture_ids": [id1]},
        follow_redirects=False,
    )
    assert ris.status_code == 200
    body2 = ris.get_data(as_text=True)
    assert "DO  - 10.1111/aaa" in body2
    assert "10.2222/bbb" not in body2
