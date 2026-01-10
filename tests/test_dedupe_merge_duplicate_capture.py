from __future__ import annotations

import json
from pathlib import Path

from paperclip.db import get_db


def _dom(*, title: str, doi: str | None) -> str:
    doi_meta = f'<meta name="citation_doi" content="{doi}">' if doi else ""
    return f"""<!doctype html>
<html>
  <head>
    <title>{title}</title>
    <meta name="citation_title" content="{title}">
    {doi_meta}
    <meta name="prism.publicationdate" content="2020-11-02">
    <meta name="citation_journal_title" content="Journal of Dedupe">
  </head>
  <body><article><p>Hello A.</p><p>Hello B.</p></article></body>
</html>
"""


CONTENT_FOR_POST = "<div><p>Hello A.</p><p>Hello B.</p></div>"


def _post_capture(client, *, source_url: str, title: str, doi: str | None) -> str:
    payload = {
        "source_url": source_url,
        "dom_html": _dom(title=title, doi=doi),
        "extraction": {"meta": {}, "content_html": CONTENT_FOR_POST, "references": []},
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


def test_doi_capture_merges_urlhash_duplicate_and_cleans_drop_dir(client, app):
    """
    Scenario:
      1) Capture A with DOI X => keep_id
      2) Capture B without DOI => drop_id (different capture)
      3) Capture B with DOI X => should select keep_id and merge drop_id into it:
           - move collection_items from drop->keep
           - delete drop capture row
           - remove drop artifacts dir (via API cleanup)
    """
    doi = "10.5555/merge.1"

    keep_id = _post_capture(
        client,
        source_url="https://example.org/keep",
        title="Keep (DOI)",
        doi=doi,
    )
    drop_id = _post_capture(
        client,
        source_url="https://example.org/drop",
        title="Drop (no DOI)",
        doi=None,
    )
    assert keep_id != drop_id

    # Put the drop capture into a collection (so we can verify it moves)
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO collections (name, created_at) VALUES (?, datetime('now'))",
            ("Merge Target",),
        )
        db.commit()
        col_id = db.execute(
            "SELECT id FROM collections WHERE name = ?",
            ("Merge Target",),
        ).fetchone()["id"]

        db.execute(
            "INSERT OR IGNORE INTO collection_items(collection_id, capture_id, added_at) VALUES(?, ?, datetime('now'))",
            (col_id, drop_id),
        )
        db.commit()

    # Sanity: drop artifacts dir exists before merge
    artifacts_root = Path(app.config["ARTIFACTS_DIR"])
    drop_dir = artifacts_root / drop_id
    keep_dir = artifacts_root / keep_id
    assert drop_dir.exists()
    assert keep_dir.exists()

    # Now capture the DROP url but with the DOI => triggers merge
    id3 = _post_capture(
        client,
        source_url="https://example.org/drop",
        title="Drop URL (now has DOI)",
        doi=doi,
    )
    assert id3 == keep_id  # DOI capture should win

    # Drop capture should be gone from DB and artifacts cleaned up by API route
    with app.app_context():
        db = get_db()
        row_drop = db.execute(
            "SELECT id FROM captures WHERE id = ? LIMIT 1",
            (drop_id,),
        ).fetchone()
        assert row_drop is None

        # Membership moved to keep_id
        rows = db.execute(
            "SELECT capture_id FROM collection_items WHERE collection_id = ?",
            (col_id,),
        ).fetchall()
        assert {r["capture_id"] for r in rows} == {keep_id}

    assert not drop_dir.exists()
