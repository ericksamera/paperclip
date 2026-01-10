from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Recognize headings that look like typical paper sections.
# We keep this conservative: fewer false positives, and it still works well for journal HTML->text.
# Accept: "Introduction", "1 Introduction", "Materials and Methods", "DISCUSSION", etc.
_HEADING_LINE_RX = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)*)\s+)?([A-Za-z][A-Za-z0-9 \-–—,:;()]{2,120})\s*$"
)

# Avoid treating sentence lines as headings (common in scraped text).
_HEADING_BAD_END_RX = re.compile(r"[.?!]\s*$")

# Canonical section kinds (extend later as needed)
_CANON_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("abstract", re.compile(r"^\s*abstract\s*$", re.I)),
    ("introduction", re.compile(r"^\s*(introduction|background)\s*$", re.I)),
    (
        "methods",
        re.compile(r"^\s*(methods?|materials\s+and\s+methods?|methodology)\s*$", re.I),
    ),
    ("results", re.compile(r"^\s*results?\s*$", re.I)),
    ("discussion", re.compile(r"^\s*discussion\s*$", re.I)),
    ("conclusion", re.compile(r"^\s*(conclusion|conclusions)\s*$", re.I)),
    (
        "references",
        re.compile(
            r"^\s*(references|bibliography|works cited|literature cited|citations)\s*$",
            re.I,
        ),
    ),
    (
        "acknowledgements",
        re.compile(r"^\s*(acknowledg(e)?ments?|acknowledgments)\s*$", re.I),
    ),
    ("funding", re.compile(r"^\s*funding\s*$", re.I)),
    (
        "conflicts",
        re.compile(r"^\s*(conflicts? of interest|competing interests?)\s*$", re.I),
    ),
]


def _norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def classify_heading(title: str) -> str:
    t = _norm_space(title)
    for kind, rx in _CANON_RULES:
        if rx.match(t):
            return kind
    return "other"


def looks_like_heading(line: str) -> bool:
    """
    Conservative heading detector on a single line of already-extracted article_text.
    """
    ln = (line or "").strip()
    if not ln:
        return False
    if len(ln) < 3 or len(ln) > 140:
        return False
    if _HEADING_BAD_END_RX.search(ln):
        return False

    m = _HEADING_LINE_RX.match(ln)
    if not m:
        return False

    title = _norm_space(m.group(2) or "")
    if not title:
        return False

    # Avoid obvious non-headings: very long "headings" or those with too many words.
    words = title.split()
    if len(words) > 12:
        return False

    # Avoid heading candidates that start with common paragraph starters.
    if (
        title[:15]
        .lower()
        .startswith(("this ", "we ", "in this ", "however ", "therefore "))
    ):
        return False

    return True


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    kind: str
    text: str

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "text": self.text,
        }


def split_into_sections(article_text: str) -> list[dict[str, Any]]:
    """
    Input: ParseResult.article_text (usually newline-separated headings + paragraphs).
    Output: list of sections in order, each with id/title/kind/text.
    """
    raw_lines = (article_text or "").splitlines()
    lines = [_norm_space(ln) for ln in raw_lines]
    # Keep blank lines as separators, but don't emit them.
    # We do NOT join paragraphs; we preserve newlines for later prompt/citation work.
    sections: list[Section] = []

    cur_title = "Body"
    cur_kind = "other"
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, cur_title, cur_kind
        text = "\n".join([x for x in buf if x.strip()]).strip()
        if not text:
            buf = []
            return
        sid = f"s{len(sections)+1:02d}"
        sections.append(Section(id=sid, title=cur_title, kind=cur_kind, text=text))
        buf = []

    for ln in lines:
        if not ln.strip():
            # Preserve paragraph breaks within a section
            if buf and buf[-1] != "":
                buf.append("")
            continue

        if looks_like_heading(ln):
            # Start a new section
            flush()
            cur_title = ln
            cur_kind = classify_heading(cur_title)
            continue

        buf.append(ln)

    flush()

    # If we ended up with a single "Body" section that contains recognizable headings
    # but they were missed, that's fine; this keeps false positives down.
    return [s.to_json() for s in sections]


def build_sections_meta(article_text: str) -> dict[str, Any]:
    secs = split_into_sections(article_text)
    return {"sections": secs, "sections_count": len(secs)}
