# services/server/captures/text_utils.py
from __future__ import annotations

import re
from typing import Iterable, List, Set

# Simple word regex: alphabetic tokens at least 3 chars, allowing internal dashes.
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")

# A small built-in base stopword set. This is deliberately minimal; if
# scikit-learn is installed we'll augment it below.
_BASE_STOP: Set[str] = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "here",
    "him",
    "his",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "me",
    "more",
    "most",
    "my",
    "no",
    "not",
    "of",
    "on",
    "or",
    "our",
    "out",
    "she",
    "so",
    "such",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "too",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "you",
    "your",
}


def stopwords(extra: Iterable[str] | None = None) -> Set[str]:
    """
    Return the stopword set used for simple tokenization.

    - Starts from a small built-in English list.
    - If scikit-learn is installed, union with ENGLISH_STOP_WORDS.
    - Optionally union with any extra words provided.
    """
    base: Set[str] = set(_BASE_STOP)
    try:
        # Optional dependency; swallow import errors.
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS  # type: ignore

        base |= set(ENGLISH_STOP_WORDS)
    except Exception:
        pass

    if extra:
        base |= {w.lower() for w in extra}

    return base


STOP: Set[str] = stopwords()


def tokenize(txt: str) -> List[str]:
    """
    Very simple word tokenizer:

      - finds "wordish" tokens via _WORD_RE
      - lowercases
      - drops stopwords

    This is used by dedup and some QA/word-frequency views.
    """
    if not txt:
        return []
    words = _WORD_RE.findall(txt)
    return [w.lower() for w in words if w and w.lower() not in STOP]
