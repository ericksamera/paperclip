from __future__ import annotations

import re
from typing import Any

from bs4 import Tag

from ...sectionizer import _split_heading_number, classify_heading, kinds_for_kind

_PMC_REF_SECTION_IDS = ("ref-list", "references", "bib")
_PMC_SKIP_CONTAINER_TAGS = {"footer"}
_KEYWORDS_SECTION_CLASS = "kwd-group"


def _norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _pmc_heading_for_section(sec: Tag) -> tuple[int, str]:
    h = sec.find(["h2", "h3", "h4"], class_=re.compile(r"\bpmc_sec_title\b", re.I))
    if h is None:
        h = sec.find(["h2", "h3", "h4"])
    if h is None:
        return 2, ""
    name = h.name.lower()
    level = 2 if name == "h2" else 3 if name == "h3" else 4
    title = _norm_space(h.get_text(" ", strip=True))
    return level, title


def _pmc_section_text(sec: Tag) -> str:
    parts: list[str] = []
    for node in sec.find_all(["p", "li"]):
        if node.name == "li" and node.find("p") is not None:
            continue
        t = _norm_space(node.get_text(" ", strip=True))
        if t:
            parts.append(t)
    return "\n".join(parts).strip()


def pmc_sections_from_html(body_root: Tag) -> list[dict[str, Any]]:
    """
    Extract stable sections from PMC HTML.

    Adds:
      - number (if heading is numbered, like "2.1 Something")
      - kinds (multi-tag list)
    """
    sections: list[dict[str, Any]] = []

    # Stack of (level, id) to assign parent_id based on heading nesting.
    stack: list[tuple[int, str]] = []

    def next_id() -> str:
        return f"s{len(sections)+1:02d}"

    for sec in body_root.find_all("section", recursive=True):
        sid = str(sec.get("id") or "")
        sid_l = sid.lower()
        classes = " ".join(sec.get("class") or [])

        if any(k in sid_l for k in _PMC_REF_SECTION_IDS) or "ref-list" in classes:
            continue
        if sec.name in _PMC_SKIP_CONTAINER_TAGS:
            continue

        # Keywords block
        if _KEYWORDS_SECTION_CLASS in classes:
            txt = _pmc_section_text(sec)
            if txt:
                new_id = next_id()
                out: dict[str, Any] = {
                    "id": new_id,
                    "title": "Keywords",
                    "kind": "keywords",
                    "kinds": kinds_for_kind("keywords"),
                    "text": txt,
                    "level": 3,
                }
                parent_id = next((pid for lvl, pid in reversed(stack) if lvl < 3), None)
                if parent_id:
                    out["parent_id"] = parent_id

                sections.append(out)

                while stack and stack[-1][0] >= out["level"]:
                    stack.pop()
                stack.append((out["level"], new_id))
            continue

        level, raw_title = _pmc_heading_for_section(sec)
        is_abstract = ("abstract" in classes.lower()) or sid_l.startswith("abstract")

        txt = _pmc_section_text(sec)
        if not txt:
            continue
        if not raw_title and not is_abstract:
            continue

        num, clean_title = _split_heading_number(raw_title or "")
        title = clean_title or (raw_title or "")
        kind = "abstract" if is_abstract else classify_heading(title or "Body")

        new_id = next_id()
        parent_id = next((pid for lvl, pid in reversed(stack) if lvl < level), None)

        out: dict[str, Any] = {
            "id": new_id,
            "title": title or ("Abstract" if is_abstract else "Section"),
            "kind": kind,
            "kinds": kinds_for_kind(kind),
            "text": txt,
            "level": level,
        }
        if num:
            out["number"] = num
        if parent_id:
            out["parent_id"] = parent_id

        sections.append(out)

        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, new_id))

    return sections
