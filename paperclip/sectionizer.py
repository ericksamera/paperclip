from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Text-based sectionizer (generic use)

# Capture optional leading numbering and a heading-ish remainder.
# Examples:
#   "1. Introduction" -> num="1", title="Introduction"
#   "3.2 Methods"     -> num="3.2", title="Methods"
#   "2) Results"      -> num="2", title="Results"
_HEADING_WITH_NUM_RX = re.compile(
    r"^\s*(?:(?P<num>\d+(?:\.\d+)*)\s*[.)]\s+)?(?P<title>.+?)\s*$",
    re.UNICODE,
)

# Unicode-friendly heading line: must start with a unicode letter (not digit/underscore),
# then allow common punctuation (including curly apostrophes).
_HEADING_LINE_RX = re.compile(
    r"^\s*([^\W\d_][\w \-–—,:;()'’/]{2,160})\s*$",
    re.UNICODE,
)

_HEADING_BAD_END_RX = re.compile(r"[.?!]\s*$")
_KEYWORDS_PREFIX_RX = re.compile(r"^\s*keywords?\s*:\s*(.+)\s*$", re.I)

# Combined headings (common in journals)
_RESULTS_AND_DISCUSSION_RX = re.compile(
    r"^\s*(results?\s*(and|&)\s*discussion|discussion\s*(and|&)\s*results?)\s*$",
    re.I,
)

_CANON_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("abstract", re.compile(r"^\s*abstract\s*$", re.I)),
    ("keywords", re.compile(r"^\s*keywords?\s*$", re.I)),
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
    ("author_contributions", re.compile(r"^\s*author contributions?\s*$", re.I)),
]


def _norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _split_heading_number(line: str) -> tuple[str | None, str]:
    """
    Returns (number, clean_title).
    """
    ln = _norm_space(line)
    m = _HEADING_WITH_NUM_RX.match(ln)
    if not m:
        return None, ln
    num = (m.group("num") or "").strip() or None
    title = _norm_space(m.group("title") or "")
    return num, title


def classify_heading(title: str) -> str:
    """
    Canonical kind classification for headings.
    IMPORTANT: strips leading numbering (e.g. "1. Introduction") before matching.
    """
    t = _norm_space(title)

    # Allow "Keywords: ..." inputs to classify as keywords
    if _KEYWORDS_PREFIX_RX.match(t):
        return "keywords"

    _num, clean = _split_heading_number(t)
    clean = _norm_space(clean)

    # Combined headings
    if _RESULTS_AND_DISCUSSION_RX.match(clean):
        return "results_discussion"

    for kind, rx in _CANON_RULES:
        if rx.match(clean):
            return kind
    return "other"


def kinds_for_kind(kind: str) -> list[str]:
    """
    Normalized multi-tag list for retrieval.
    """
    if kind == "results_discussion":
        return ["results", "discussion"]
    return [kind]


def looks_like_heading(line: str) -> bool:
    ln = (line or "").strip()
    if not ln:
        return False
    if len(ln) < 3 or len(ln) > 220:
        return False
    if _HEADING_BAD_END_RX.search(ln):
        return False

    # Allow "Keywords: ..." as a pseudo-heading line
    if _KEYWORDS_PREFIX_RX.match(ln):
        return True

    num, rest = _split_heading_number(ln)
    candidate = rest if num else _norm_space(ln)

    if _HEADING_BAD_END_RX.search(candidate):
        return False
    if not _HEADING_LINE_RX.match(candidate):
        return False
    if len(candidate.split()) > 16:
        return False
    if (
        candidate[:15]
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
    level: int = 2
    number: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "kinds": kinds_for_kind(self.kind),
            "text": self.text,
            "level": self.level,
        }
        if self.number:
            out["number"] = self.number
        return out


def split_into_sections(article_text: str) -> list[dict[str, Any]]:
    raw_lines = (article_text or "").splitlines()
    lines = [_norm_space(ln) for ln in raw_lines]

    sections: list[Section] = []
    cur_title = "Body"
    cur_kind = "other"
    cur_number: str | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, cur_title, cur_kind, cur_number
        text = "\n".join([x for x in buf if x.strip()]).strip()
        if not text:
            buf = []
            return
        sid = f"s{len(sections)+1:02d}"
        sections.append(
            Section(
                id=sid,
                title=cur_title,
                kind=cur_kind,
                text=text,
                level=2,
                number=cur_number,
            )
        )
        buf = []

    for ln in lines:
        if not ln.strip():
            if buf and buf[-1] != "":
                buf.append("")
            continue

        if looks_like_heading(ln):
            # "Keywords: a, b, c" carries content on same line.
            mkw = _KEYWORDS_PREFIX_RX.match(ln)
            if mkw:
                flush()
                cur_title = "Keywords"
                cur_kind = "keywords"
                cur_number = None
                kw_text = _norm_space(mkw.group(1) or "")
                if kw_text:
                    buf.append(f"Keywords: {kw_text}")
                continue

            flush()

            num, clean = _split_heading_number(ln)
            cur_number = num
            cur_title = clean
            cur_kind = classify_heading(cur_title)
            continue

        buf.append(ln)

    flush()
    return [s.to_json() for s in sections]


def build_sections_meta(article_text: str) -> dict[str, Any]:
    secs = split_into_sections(article_text)
    return {"sections": secs, "sections_count": len(secs)}
