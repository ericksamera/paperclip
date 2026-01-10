from __future__ import annotations

import re
from typing import Any


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _md_escape_heading(s: str) -> str:
    # Minimal: avoid weird heading rendering
    s = (s or "").strip()
    s = s.replace("\r", " ").replace("\n", " ")
    return s


def render_paper_markdown(
    *,
    title: str,
    source_url: str,
    doi: str,
    container_title: str,
    year: int | None,
    sections: list[dict[str, Any]] | None,
    references_text: str,
) -> str:
    """
    Deterministic “paper bundle” markdown for LLM upload / downstream compilation.

    - Uses section titles as headings.
    - Does not invent content.
    """
    lines: list[str] = []

    title = _norm(title) or "Untitled"
    lines.append(f"# {title}")
    lines.append("")

    meta_bits: list[str] = []
    if doi:
        meta_bits.append(f"DOI: `{doi}`")
    if container_title:
        meta_bits.append(container_title.strip())
    if isinstance(year, int) and year:
        meta_bits.append(str(year))
    if source_url:
        meta_bits.append(source_url.strip())

    if meta_bits:
        lines.append("**" + " · ".join(meta_bits) + "**")
        lines.append("")

    secs = sections if isinstance(sections, list) else []
    for s in secs:
        stitle = str(s.get("title") or "").strip() or "Section"
        skind = str(s.get("kind") or "").strip()
        text = str(s.get("text") or "").strip()
        if not text:
            continue

        # If the section is the default “Body”, don’t add a redundant heading.
        if stitle == "Body" and skind == "other":
            lines.append(text)
            lines.append("")
            continue

        lines.append(f"## {_md_escape_heading(stitle)}")
        lines.append(text)
        lines.append("")

    refs = (references_text or "").strip()
    if refs:
        lines.append("## References")
        lines.append(refs)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
