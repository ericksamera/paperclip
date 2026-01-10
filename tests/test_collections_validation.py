from __future__ import annotations

from paperclip.db import get_db


def _count_collections(app) -> int:
    with app.app_context():
        db = get_db()
        return int(db.execute("SELECT COUNT(1) AS n FROM collections").fetchone()["n"])


def _get_collection_id(app, name: str) -> int | None:
    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT id FROM collections WHERE name = ?", (name,)
        ).fetchone()
        return int(row["id"]) if row else None


def _get_collection_name(app, collection_id: int) -> str | None:
    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT name FROM collections WHERE id = ?", (collection_id,)
        ).fetchone()
        return str(row["name"]) if row else None


def test_create_collection_rejects_empty_name(client, app):
    before = _count_collections(app)

    r = client.post(
        "/collections/create/",
        data={"name": "   "},
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Name required." in body

    after = _count_collections(app)
    assert after == before


def test_create_collection_duplicate_name_is_rejected(client, app):
    before = _count_collections(app)

    r1 = client.post(
        "/collections/create/",
        data={"name": "My Collection"},
        follow_redirects=True,
    )
    assert r1.status_code == 200
    body1 = r1.get_data(as_text=True)
    assert "Collection created." in body1

    mid = _count_collections(app)
    assert mid == before + 1

    # Duplicate
    r2 = client.post(
        "/collections/create/",
        data={"name": "My Collection"},
        follow_redirects=True,
    )
    assert r2.status_code == 200
    body2 = r2.get_data(as_text=True)
    assert "Collection already exists." in body2

    after = _count_collections(app)
    assert after == mid


def test_rename_collection_rejects_empty_name(client, app):
    client.post(
        "/collections/create/",
        data={"name": "A"},
        follow_redirects=True,
    )
    cid = _get_collection_id(app, "A")
    assert cid is not None

    r = client.post(
        f"/collections/{cid}/rename/",
        data={"name": "   "},
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Name required." in body

    assert _get_collection_name(app, cid) == "A"


def test_rename_collection_to_existing_name_is_rejected(client, app):
    # Create two collections
    client.post("/collections/create/", data={"name": "Alpha"}, follow_redirects=True)
    client.post("/collections/create/", data={"name": "Beta"}, follow_redirects=True)

    alpha_id = _get_collection_id(app, "Alpha")
    beta_id = _get_collection_id(app, "Beta")
    assert alpha_id is not None
    assert beta_id is not None

    # Attempt rename Beta -> Alpha (should fail due to UNIQUE(name))
    r = client.post(
        f"/collections/{beta_id}/rename/",
        data={"name": "Alpha"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Collection name already exists." in body

    # Verify DB unchanged
    assert _get_collection_name(app, alpha_id) == "Alpha"
    assert _get_collection_name(app, beta_id) == "Beta"
