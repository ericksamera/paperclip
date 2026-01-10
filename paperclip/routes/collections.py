from __future__ import annotations

from flask import Flask, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..services import collections_service
from ..timeutil import utc_now_iso
from ..tx import db_tx


def register(app: Flask) -> None:
    @app.get("/collections/")
    def collections_page():
        db = get_db()
        collections = collections_service.list_collections_with_counts(db)
        return render_template("collections.html", collections=collections)

    @app.post("/collections/create/")
    def collections_create():
        name = (request.form.get("name") or "").strip()
        now = utc_now_iso()

        with db_tx() as db:
            res = collections_service.create_collection(db, name=name, created_at=now)

        flash(res.message, res.category)
        return redirect(url_for("collections_page"))

    @app.post("/collections/<int:collection_id>/rename/")
    def collections_rename(collection_id: int):
        name = (request.form.get("name") or "").strip()

        with db_tx() as db:
            res = collections_service.rename_collection(
                db, collection_id=collection_id, name=name
            )

        flash(res.message, res.category)
        return redirect(url_for("collections_page"))

    @app.post("/collections/<int:collection_id>/delete/")
    def collections_delete(collection_id: int):
        with db_tx() as db:
            res = collections_service.delete_collection(db, collection_id=collection_id)

        flash(res.message, res.category)
        return redirect(url_for("collections_page"))
