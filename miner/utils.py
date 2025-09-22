from __future__ import annotations
from pathlib import Path
import json
import re
import unicodedata
from typing import Optional, Iterable, Any

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

def html_to_text(html: Optional[str]) -> str:
    if not html:
        return ""
    txt = _HTML_TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", txt).strip()

def uniq(seq: Iterable[Any]) -> list:
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def slug(s: str, maxlen: int = 48) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("-")
    return s.lower() or "item"

def normalize_title(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s\-:]+", "", s)
    return s

def safe_json(obj, path: Path):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), "utf-8")

def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "item"
