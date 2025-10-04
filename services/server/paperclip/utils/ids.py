from __future__ import annotations

import re

_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)\s*", re.I)


def norm_doi(s: str | None) -> str:
    """
    Normalize a DOI field coming from anywhere:
      - strip leading 'https://doi.org/' or 'doi:' prefixes
      - trim & lowercase
    Returns "" when empty/None.
    """
    if not s:
        return ""
    return _DOI_PREFIX.sub("", s.strip()).lower()
