from __future__ import annotations

import json

from paperclip.db import get_db


def _dom(*, doi: str, title: str) -> str:
    return f"""<!doctype html>
<html>
  <head>
    <title>{title}</title>
    <meta name="citation_title" content="{title}">
    <meta name="citation_doi" content="{doi}">
    <meta name="prism.publicationdate" content="2020-11-02">
    <meta name="citation_journal_title" content="Journal of Search">
  </head>
  <body><article><p>Hello A.</p><p>Hello B.</p></article></body>
</html>
"""


CONTENT_FOR_POST = "<div><p>Hello A.</p><p>Hello B.</p></div>"


def _post_capture(client, *, source_url: str, doi: str, title: str) -> str:
    payload = {
        "source_url": source_url,
        "dom_html": _dom(doi=doi, title=title),
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }
    r = client.post(
        "/api/captures/", data=json.dumps(payload), content_type="application/json"
    )
    assert r.status_code in (200, 201)
    return r.get_json()["capture_id"]


def test_api_library_pagination_and_has_more(client):
    _post_capture(
        client,
        source_url="https://example.org/a",
        doi="10.1000/aaa",
        title="Alpha Paper",
    )
    _post_capture(
        client,
        source_url="https://example.org/b",
        doi="10.2000/bbb",
        title="Beta Paper",
    )
    _post_capture(
        client,
        source_url="https://example.org/c",
        doi="10.3000/ccc",
        title="Gamma Paper",
    )

    p1 = client.get("/api/library/?page=1&page_size=2")
    assert p1.status_code == 200
    d1 = p1.get_json()
    assert d1["page"] == 1
    assert d1["page_size"] == 2
    assert d1["total"] == 3
    assert len(d1["captures"]) == 2
    assert d1["has_more"] is True

    p2 = client.get("/api/library/?page=2&page_size=2")
    assert p2.status_code == 200
    d2 = p2.get_json()
    assert d2["page"] == 2
    assert d2["page_size"] == 2
    assert d2["total"] == 3
    assert len(d2["captures"]) == 1
    assert d2["has_more"] is False


def test_api_library_search_by_doi_and_title(client):
    id1 = _post_capture(
        client,
        source_url="https://example.org/search1",
        doi="10.7777/findme",
        title="Find Me Paper",
    )
    _post_capture(
        client,
        source_url="https://example.org/search2",
        doi="10.8888/other",
        title="Other Paper",
    )

    s1 = client.get("/api/library/?q=10.7777/findme")
    assert s1.status_code == 200
    d = s1.get_json()
    assert d["total"] >= 1
    assert any(c["id"] == id1 for c in d["captures"])

    s2 = client.get("/api/library/?q=Find Me")
    assert s2.status_code == 200
    d2 = s2.get_json()
    assert d2["total"] >= 1
    assert any(c["id"] == id1 for c in d2["captures"])


def test_api_library_collection_filter(client, app):
    id_in = _post_capture(
        client,
        source_url="https://example.org/in",
        doi="10.4242/in",
        title="In Collection",
    )
    _post_capture(
        client,
        source_url="https://example.org/out",
        doi="10.4242/out",
        title="Out of Collection",
    )

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO collections (name, created_at) VALUES (?, datetime('now'))",
            ("Filter Collection",),
        )
        db.commit()
        col_id = db.execute(
            "SELECT id FROM collections WHERE name = ?",
            ("Filter Collection",),
        ).fetchone()["id"]

        db.execute(
            "INSERT OR IGNORE INTO collection_items(collection_id, capture_id, added_at) VALUES(?, ?, datetime('now'))",
            (col_id, id_in),
        )
        db.commit()

    r = client.get(f"/api/library/?collection={col_id}")
    assert r.status_code == 200
    d = r.get_json()
    assert d["total"] == 1
    assert len(d["captures"]) == 1
    assert d["captures"][0]["id"] == id_in
