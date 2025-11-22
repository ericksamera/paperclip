from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection

from captures.models import Capture
from captures.search import ensure_fts, upsert_capture


class Command(BaseCommand):
    help = "Rebuild the SQLite FTS index from all captures."

    def handle(self, *args, **opts):
        ensure_fts()
        with connection.cursor() as c:
            c.execute("DELETE FROM capture_fts")
        for cap in Capture.objects.all().iterator():
            upsert_capture(cap)
        self.stdout.write(self.style.SUCCESS("FTS rebuilt."))
