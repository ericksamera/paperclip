from __future__ import annotations
from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.db.models.signals import post_save, post_delete


class CapturesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "captures"

    def ready(self):
        # Import inside ready() so Django app loading stays clean (no DB work here).
        from .models import Capture
        from .search import upsert_capture, delete_capture, ensure_fts

        # --- FTS live index hooks (pure Python wiring; no queries) ---
        def _on_save(sender, instance: Capture, **kwargs):
            try:
                upsert_capture(instance)
            except Exception:
                # FTS is best-effort in dev; never crash saves
                pass

        def _on_delete(sender, instance: Capture, **kwargs):
            try:
                delete_capture(instance.id)
            except Exception:
                pass

        post_save.connect(_on_save, sender=Capture, weak=False)
        post_delete.connect(_on_delete, sender=Capture, weak=False)

        # --- Per-connection initialization (runs AFTER DB connects) ---
        def _on_connection(sender, connection, **kwargs):
            try:
                # Only for SQLite: set dev-friendly PRAGMAs
                if getattr(connection, "vendor", "") == "sqlite":
                    with connection.cursor() as c:
                        c.execute("PRAGMA journal_mode=WAL;")
                        c.execute("PRAGMA synchronous=NORMAL;")
                        c.execute("PRAGMA foreign_keys=ON;")
                # Ensure FTS virtual table exists (idempotent; SQLite only)
                ensure_fts(connection)
            except Exception:
                # Safe to ignore in environments without FTS5, etc.
                pass

        connection_created.connect(_on_connection, weak=False)
