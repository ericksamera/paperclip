from __future__ import annotations

from paperclip.db import get_db
from paperclip.services import captures_service, collections_service
from paperclip.services.types import ActionResult


def test_actionresult_is_canonical(app):
    # The service modules should re-export the canonical ActionResult type
    assert captures_service.ActionResult is ActionResult
    assert collections_service.ActionResult is ActionResult


def test_actionresult_optional_fields_exist(app):
    # Even services that don't currently use these fields should still get them
    with app.app_context():
        db = get_db()

        r1 = collections_service.create_collection(
            db, name="", created_at="2026-01-10T00:00:00Z"
        )
        assert isinstance(r1, ActionResult)
        assert r1.changed_count == 0
        assert r1.cleanup_paths == []

        r2 = captures_service.set_capture_collections(
            db,
            capture_id="does-not-exist",
            selected_ids=set(),
            now="2026-01-10T00:00:00Z",
        )
        assert isinstance(r2, ActionResult)
        assert r2.ok is False
        assert r2.category == "error"
        assert r2.changed_count == 0
        assert r2.cleanup_paths == []
