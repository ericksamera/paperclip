# services/server/captures/keywords.py
from __future__ import annotations
# Single source of truth for keyword tokenization across the server codebase.
from captures.site_parsers.base import split_keywords_block as split_keywords

__all__ = ["split_keywords"]
