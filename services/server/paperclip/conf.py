# services/server/paperclip/conf.py
from __future__ import annotations

# Behavior toggles (dev-friendly defaults)
AUTO_ENRICH = True           # run Crossref on the page DOI + every reference DOI at ingest
ENRICH_TIMEOUT = 5           # seconds; used inside captures/xref.py

# Network / identification
USER_AGENT = "Paperclip/0.1 (+https://example.invalid)"

# Limits / safety
MAX_REFS_TO_ENRICH = 500     # hard cap so a page can’t stall ingest forever
