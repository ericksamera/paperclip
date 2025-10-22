from __future__ import annotations

import re
from typing import Any

# DOI pattern from Crossref guidance (relaxed tail)
_DOI_RX = re.compile(r"10\.\d{4,9}/[^\s<>\"\'\t\r\n]+", re.I)


def norm_doi(doi: str | None) -> str:
    """
    Normalize a DOI:
      • strip whitespace / punctuation
      • drop leading 'doi:' and DOI URLs (http[s]://(dx.)?doi.org/)
      • lower-case (DOIs are case-insensitive)
      • if the input contains a DOI inside text, extract the first DOI-looking token
      • return '' if nothing sensible
    """
    s = (doi or "").strip()
    if not s:
        return ""
    s = s.replace("\u200b", "").strip()
    # Remove URL prefixes
    s = re.sub(r"(?i)^\s*https?://(?:dx\.)?doi\.org/", "", s)
    # Remove 'doi:' prefix
    s = re.sub(r"(?i)^\s*doi\s*:\s*", "", s)
    s = s.strip().strip(".,;:)]}\"'")
    m = _DOI_RX.search(s)
    core = m.group(0) if m else s
    # If it still doesn't look like a DOI, bail out
    if not _DOI_RX.match(core):
        return ""
    return core.lower()


def safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)  # type: ignore[arg-type]
    except Exception:
        return default
