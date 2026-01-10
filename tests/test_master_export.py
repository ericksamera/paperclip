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
    <meta name="citation_journal_title" content="Journal of Master Export">
  </head>
  <body>
    <article>
      <h2>Introduction</h2>
      <p>Hello from {title}.</p>
      <h2>References</h2>
      <ol><li>Ref for {title}.</li></ol>
    </article>
  </body>
</html>
"""


CONTENT_FOR_POST = "<div><p>Fallback content.</p></div>"


def _post_capture(client, *, source_url: str, doi: str, title: str) -> str:
    payload = {
        "source_url": source_url,
        "dom_html": _dom(doi=doi, title=title),
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
        "rendered": {},
        "client": {"ext": "chrome", "v": "0.1.0"},
    }
    r = client.post(
        "/api/captures/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert r.status_code in (200, 201)
    return r.get_json()["capture_id"]


def test_export_master_md_all_includes_multiple_papers(client):
    _post_capture(
        client,
        source_url="https://example.org/m1",
        doi="10.1111/m1",
        title="Master One",
    )
    _post_capture(
        client,
        source_url="https://example.org/m2",
        doi="10.2222/m2",
        title="Master Two",
    )

    r = client.get("/exports/master.md/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)

    # header
    assert body.startswith("# Paperclip Master Export")
    # includes both
    assert "Master One" in body
    assert "Master Two" in body
    # separator
    assert "\n---\n" in body
    # references present (from paper.md)
    assert "## References" in body

    cd = r.headers.get("Content-Disposition", "")
    assert cd.endswith('.md"')


def test_export_master_md_collection_filters(client, app):
    id1 = _post_capture(
        client,
        source_url="https://example.org/c1",
        doi="10.3333/c1",
        title="In Collection",
    )
    _post_capture(
        client,
        source_url="https://example.org/c2",
        doi="10.4444/c2",
        title="Out of Collection",
    )

    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO collections (name, created_at) VALUES (?, datetime('now'))",
            ("Only These",),
        )
        db.commit()
        col_id = db.execute(
            "SELECT id FROM collections WHERE name = ?",
            ("Only These",),
        ).fetchone()["id"]
        db.execute(
            "INSERT OR IGNORE INTO collection_items(collection_id, capture_id, added_at) VALUES(?, ?, datetime('now'))",
            (col_id, id1),
        )
        db.commit()

    r = client.get(f"/exports/master.md/?collection={col_id}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)

    assert "In Collection" in body
    assert "Out of Collection" not in body
    assert "Only These" in body  # title includes collection name


def test_export_selected_master_md_only_includes_selected(client):
    id1 = _post_capture(
        client,
        source_url="https://example.org/s1",
        doi="10.5555/s1",
        title="Selected One",
    )
    _post_capture(
        client,
        source_url="https://example.org/s2",
        doi="10.6666/s2",
        title="Selected Two",
    )

    r = client.post(
        "/exports/master.md/selected/",
        data={"capture_ids": [id1]},
        follow_redirects=False,
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)

    assert "Selected One" in body
    assert "Selected Two" not in body
    assert "Selected" in body.splitlines()[0] or "Selected" in body
