# services/server/paperclip/conf.py
from __future__ import annotations

import os

# Behavior toggles (env-driven; fast-by-default).
# When true, we fire a background job to enrich *references* after ingest.
AUTO_ENRICH = os.getenv("PAPERCLIP_AUTO_ENRICH", "0").lower() in {"1", "true", "yes"}

# NEW: try Crossref immediately for the *main capture* when a DOI is present.
# This is synchronous, cached, and fast (short timeout) so artifacts are standardized at save time.
ENRICH_ON_CAPTURE = os.getenv("PAPERCLIP_ENRICH_ON_CAPTURE", "1").lower() in {"1", "true", "yes"}

ENRICH_TIMEOUT = int(os.getenv("PAPERCLIP_ENRICH_TIMEOUT", "4"))  # seconds
MAX_REFS_TO_ENRICH = int(os.getenv("PAPERCLIP_MAX_REFS", "50"))  # safety cap

# Network / identification (used by Crossref)
USER_AGENT = os.getenv("PAPERCLIP_USER_AGENT", "Paperclip/0.1 (+https://example.invalid)")
