# services/server/analysis/text.py
from __future__ import annotations
import re
from typing import List, Set

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")

_BASE_STOP: Set[str] = {
    "the","and","for","with","from","that","this","those","these","into","onto","between","among","within",
    "on","in","at","by","of","to","as","is","are","was","were","be","been","being","it","its","a","an",
    "or","but","not","so","such","than","then","via","we","our","you","your","their","they","he","she",
    "his","her","which","who","whom","whose","where","when","while","during","per","each","also","using",
    "used","use","new","one","two","three","more","most","can","may","might","results","methods","method",
    "conclusion","conclusions","figure","figures","table","tables","et","al","study","studies","based","over",
}

def stopwords() -> Set[str]:
    try:
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS  # type: ignore
        return set(ENGLISH_STOP_WORDS) | _BASE_STOP
    except Exception:
        return set(_BASE_STOP)

STOP = stopwords()

def tokenize(txt: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(txt or "") if w.lower() not in STOP]
