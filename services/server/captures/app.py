# services/server/captures/app.py
from __future__ import annotations

from contextlib import suppress

from django.apps import AppConfig
from django.core.cache import cache
from django.db.backends.signals import connection_created
from django.db.models.signals import post_delete, post_save


class CapturesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "captures"

    def ready(self):
        # Import inside ready() so Django app loading stays clean.
        from .models import Capture
        from .search import (  # reindex_all imported lazily below
            delete_capture,
            ensure_fts,
            upsert_capture,
        )

        # --- FTS live index hooks (cheap) ---
        def _on_save(sender, instance: Capture, **kwargs):
            with suppress(Exception):
                upsert_capture(instance)
            with suppress(Exception):
                cache.delete("facets:all")

        def _on_delete(sender, instance: Capture, **kwargs):
            with suppress(Exception):
                delete_capture(instance.id)
            with suppress(Exception):
                cache.delete("facets:all")

        post_save.connect(_on_save, sender=Capture, weak=False)
        post_delete.connect(_on_delete, sender=Capture, weak=False)

        # --- Per-connection initialization (runs AFTER DB connects) ---
        def _on_connection(sender, connection, **kwargs):
            try:
                # Dev-friendly PRAGMAs for SQLite
                if getattr(connection, "vendor", "") == "sqlite":
                    with connection.cursor() as c:
                        c.execute("PRAGMA journal_mode=WAL;")
                        c.execute("PRAGMA synchronous=NORMAL;")
                        c.execute("PRAGMA foreign_keys=ON;")
                # Create FTS table if missing
                ensure_fts(connection)
                # NEW: Auto-populate FTS once when empty but captures exist
                try:
                    with connection.cursor() as c:
                        c.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name='capture_fts'"
                        )
                        exists = bool(c.fetchone())
                        fts_rows = cap_rows = 0
                        if exists:
                            c.execute("SELECT COUNT(*) FROM capture_fts")
                            fts_rows = int(c.fetchone()[0] or 0)
                        # Count captures regardless
                        c.execute("SELECT COUNT(*) FROM captures_capture")
                        cap_rows = int(c.fetchone()[0] or 0)
                    if cap_rows > 0 and fts_rows == 0:
                        # Lazy import to avoid cycles
                        from .search import reindex_all

                        reindex_all()
                except Exception:
                    # Never block startup on best-effort indexing
                    pass
            except Exception:
                # Never block startup
                pass

        connection_created.connect(_on_connection, weak=False)
