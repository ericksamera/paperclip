from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from captures.services.dedup import scan_and_write_dupes


class Command(BaseCommand):
    help = (
        "Scan for near-duplicate captures with MinHash/LSH and "
        "write data/analysis/dupes.json"
    )

    def handle(self, *args, **opts):
        groups = scan_and_write_dupes(threshold=0.85)
        out = settings.ANALYSIS_DIR / "dupes.json"
        if groups:
            self.stdout.write(
                self.style.SUCCESS(f"Found {len(groups)} groups. Wrote {out}.")
            )
        else:
            self.stdout.write("No near-duplicates detected.")
