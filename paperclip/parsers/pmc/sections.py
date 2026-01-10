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
    name = (h.name or "").lower()
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


def _is_ref_section(sec: Tag) -> bool:
    sid = str(sec.get("id") or "")
    sid_l = sid.lower()
    classes = " ".join(sec.get("class") or [])
    return any(k in sid_l for k in _PMC_REF_SECTION_IDS) or ("ref-list" in classes)


def pmc_sections_from_html(body_root: Tag) -> list[dict[str, Any]]:
    """
    Extract stable sections from PMC HTML.

    Key behavior:
      - Keep explicit sections (Abstract/Résumé, Tables, Acknowledgments, Footnotes, etc.)
      - ALSO create a "Body" section for the common PMC pattern where the article body
        is a sequence of top-level <p> siblings not wrapped in <section>.
      - Never include References as a section (they're extracted separately).
    """
    if not isinstance(body_root, Tag):
        return []

    sections: list[dict[str, Any]] = []
    stack: list[tuple[int, str]] = []

    # Signature set to prevent duplicates across passes
    # (title|first 80 chars of text)
    seen_sigs: set[str] = set()

    def _sig(title: str, text: str) -> str:
        return (f"{title}|{text[:80]}").casefold()

    def next_id() -> str:
        return f"s{len(sections)+1:02d}"

    def push_stack(level: int, sid: str) -> None:
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, sid))

    def parent_for(level: int) -> str | None:
        return next((pid for lvl, pid in reversed(stack) if lvl < level), None)

    def append_section(
        *, title: str, kind: str, level: int, text: str, number: str | None = None
    ) -> None:
        txt = (text or "").strip()
        if not txt:
            return

        sig = _sig(title, txt)
        if sig in seen_sigs:
            return
        seen_sigs.add(sig)

        sid = next_id()
        out: dict[str, Any] = {
            "id": sid,
            "title": title,
            "kind": kind,
            "kinds": kinds_for_kind(kind),
            "text": txt,
            "level": level,
        }
        if number:
            out["number"] = number

        pid = parent_for(level)
        if pid:
            out["parent_id"] = pid

        sections.append(out)
        push_stack(level, sid)

    # ------------------------------------------------------------
    # Pass 1: walk only *direct children* to capture loose body <p>
    # ------------------------------------------------------------
    body_buf: list[str] = []

    def flush_body() -> None:
        nonlocal body_buf
        text = "\n".join([x for x in body_buf if x.strip()]).strip()
        if text:
            append_section(title="Body", kind="other", level=2, text=text)
        body_buf = []

    for child in [c for c in body_root.children if isinstance(c, Tag)]:
        if child.name in _PMC_SKIP_CONTAINER_TAGS:
            continue

        # Skip references blocks entirely
        if child.name == "section" and _is_ref_section(child):
            flush_body()
            continue

        if child.name == "section":
            classes = " ".join(child.get("class") or [])
            classes_l = classes.lower()
            sid_l = str(child.get("id") or "").lower()

            # Keywords block
            if _KEYWORDS_SECTION_CLASS in classes:
                flush_body()
                txt = _pmc_section_text(child)
                if txt:
                    append_section(title="Keywords", kind="keywords", level=3, text=txt)
                continue

            # Abstract blocks (English + translated)
            if (
                ("abstract" in classes_l)
                or sid_l.startswith("abstract")
                or sid_l.startswith("trans-abstract")
            ):
                flush_body()
                level, raw_title = _pmc_heading_for_section(child)
                title = raw_title or "Abstract"
                txt = _pmc_section_text(child)
                if txt:
                    append_section(
                        title=title or "Abstract",
                        kind="abstract",
                        level=level or 2,
                        text=txt,
                    )
                continue

            # Other "real" sections with headings
            level, raw_title = _pmc_heading_for_section(child)
            if raw_title:
                flush_body()
                num, clean_title = _split_heading_number(raw_title)
                title = clean_title or raw_title
                kind = classify_heading(title or "Section")
                txt = _pmc_section_text(child)
                if txt:
                    append_section(
                        title=title or "Section",
                        kind=kind,
                        level=level,
                        text=txt,
                        number=num,
                    )
                continue

            # Section without usable heading: treat its text as loose body
            txt = _pmc_section_text(child)
            if txt:
                body_buf.append(txt)
            continue

        # Loose <p> siblings are common PMC body
        if child.name == "p":
            t = _norm_space(child.get_text(" ", strip=True))
            if t:
                body_buf.append(t)
            continue

        # Other tags: pull paragraph descendants if present
        ps = child.find_all("p") if hasattr(child, "find_all") else []
        if ps:
            for p in ps:
                if not isinstance(p, Tag):
                    continue
                t = _norm_space(p.get_text(" ", strip=True))
                if t:
                    body_buf.append(t)

    flush_body()

    # ------------------------------------------------------------
    # Pass 2: nested sections we might have missed
    # ------------------------------------------------------------
    for sec in body_root.find_all("section", recursive=True):
        if not isinstance(sec, Tag):
            continue
        if sec.name in _PMC_SKIP_CONTAINER_TAGS:
            continue
        if _is_ref_section(sec):
            continue

        classes = " ".join(sec.get("class") or [])
        classes_l = classes.lower()
        sid_l = str(sec.get("id") or "").lower()

        if _KEYWORDS_SECTION_CLASS in classes:
            continue

        level, raw_title = _pmc_heading_for_section(sec)
        is_abstract = (
            ("abstract" in classes_l)
            or sid_l.startswith("abstract")
            or sid_l.startswith("trans-abstract")
        )
        txt = _pmc_section_text(sec)
        if not txt:
            continue

        if not raw_title and not is_abstract:
            continue

        num, clean_title = _split_heading_number(raw_title or "")
        title = clean_title or raw_title or ("Abstract" if is_abstract else "Section")
        kind = "abstract" if is_abstract else classify_heading(title or "Section")

        append_section(title=title, kind=kind, level=level or 2, text=txt, number=num)

    return sections
