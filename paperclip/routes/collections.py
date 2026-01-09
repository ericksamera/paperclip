from __future__ import annotations

from flask import Flask, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..repo import collections_repo
from ..timeutil import utc_now_iso


def register(app: Flask) -> None:
    @app.get("/collections/")
    def collections_page():
        db = get_db()
        collections = collections_repo.list_collections_with_counts(db)
        return render_template("collections.html", collections=collections)

    @app.post("/collections/create/")
    def collections_create():
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name required.", "warning")
            return redirect(url_for("collections_page"))

        db = get_db()
        collections_repo.create_collection(db, name=name, created_at=utc_now_iso())
        db.commit()

        flash("Collection created.", "success")
        return redirect(url_for("collections_page"))

    @app.post("/collections/<int:collection_id>/rename/")
    def collections_rename(collection_id: int):
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name required.", "warning")
            return redirect(url_for("collections_page"))

        db = get_db()
        collections_repo.rename_collection(db, collection_id=collection_id, name=name)
        db.commit()

        flash("Collection renamed.", "success")
        return redirect(url_for("collections_page"))

    @app.post("/collections/<int:collection_id>/delete/")
    def collections_delete(collection_id: int):
        db = get_db()
        collections_repo.delete_collection(db, collection_id=collection_id)
        db.commit()

        flash("Collection deleted.", "success")
        return redirect(url_for("collections_page"))
