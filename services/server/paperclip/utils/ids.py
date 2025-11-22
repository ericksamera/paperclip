# services/server/paperclip/utils/ids.py
from __future__ import annotations

import re
from typing import Any

# DOI pattern (registrant 1–9 digits). We keep this permissive enough to accept
# edge-case DOIs like "10.1/xyz" that appear in tests, while still requiring a
# proper "10.<digits>/" prefix.
_DOI_RX = re.compile(r"10\.\d{1,9}/[^\s<>\"'\t\r\n]+", re.I)


def norm_doi(doi: str | None) -> str:
    """
    Normalize a DOI string.

    Rules:
    - Accept anything that *contains* something DOI-shaped (10.x/…), even inside
      a longer string; pick the first DOI-looking token.
    - Strip leading/trailing whitespace and zero-width spaces.
    - Drop URL prefixes like http[s]://(dx.)?doi.org/.
    - Drop leading 'doi:' (case-insensitive).
    - Strip trailing punctuation (.,;:)]}'" etc.).
    - Return the DOI lower-cased.
    - Return '' when nothing DOI-ish is found.
    """
    s = (doi or "").strip()
    if not s:
        return ""

    # Remove zero-width spaces and trim again
    s = s.replace("\u200b", "").strip()

    # Common URL prefixes
    s = re.sub(r"(?i)^\s*https?://(?:dx\.)?doi\.org/", "", s)
    # Leading "doi:" prefix
    s = re.sub(r"(?i)^\s*doi\s*:\s*", "", s)

    # Strip surrounding punctuation that often sneaks in from copy/paste
    s = s.strip().strip(".:)]}\"'")

    # If there's a DOI-looking token inside the remaining text, take it
    m = _DOI_RX.search(s)
    core = m.group(0) if m else s

    # Bail out if the candidate still doesn't look like a DOI
    if not _DOI_RX.match(core):
        return ""

    return core.lower()


def safe_int(x: Any, default: int = 0) -> int:
    """Convert to int, returning `default` on any error."""
    try:
        return int(x)  # type: ignore[arg-type]
    except Exception:
        return default
