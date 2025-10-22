from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand

from captures.dedup import find_near_duplicates


class Command(BaseCommand):
    help = "Scan for near-duplicate captures with MinHash/LSH and write data/analysis/dupes.json"

    def handle(self, *args, **opts):
        groups = find_near_duplicates(threshold=0.85)
        out = settings.ANALYSIS_DIR / "dupes.json"
        out.write_text(json.dumps({"groups": groups}, indent=2), "utf-8")
        if groups:
            self.stdout.write(
                self.style.SUCCESS(f"Found {len(groups)} groups. Wrote {out}.")
            )
        else:
            self.stdout.write("No near-duplicates detected.")
