from __future__ import annotations

import re
from typing import Any

from .capture_dto import build_capture_dto_from_row


def _escape_bibtex(s: str) -> str:
    # Minimal escaping for BibTeX
    s = s.replace("\\", "\\\\")
    s = s.replace("{", "\\{").replace("}", "\\}")
    s = s.replace('"', '\\"')
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _bibtex_key(capture_id: str, year: int | None) -> str:
    y = str(year) if year else "nd"
    return f"pc{y}_{(capture_id or '')[:8]}"


def _norm_abstract(val: str) -> str:
    return re.sub(r"\s+", " ", (val or "")).strip()


def captures_to_bibtex(rows: list[dict[str, Any]]) -> str:
    entries: list[str] = []
    for r in rows:
        dto = build_capture_dto_from_row(r)

        cid = str(dto.get("id") or "")
        title = str(dto.get("title") or "").strip()
        url = str(dto.get("url") or "").strip()
        doi = str(dto.get("doi") or "").strip()
        year_i = dto.get("year", None)
        journal = str(dto.get("container_title") or "").strip()

        keywords = dto.get("keywords") or []
        authors = dto.get("authors") or []
        abstract = _norm_abstract(str(dto.get("abstract") or ""))

        entry_type = "article" if journal else "misc"
        key = _bibtex_key(cid, year_i if isinstance(year_i, int) else None)

        fields: list[tuple[str, str]] = []
        fields.append(("title", _escape_bibtex(title or "Untitled")))
        if authors:
            fields.append(("author", _escape_bibtex(" and ".join(authors))))
        if journal:
            fields.append(("journal", _escape_bibtex(journal)))
        if isinstance(year_i, int) and year_i:
            fields.append(("year", str(year_i)))
        if doi:
            fields.append(("doi", _escape_bibtex(doi)))
        if url:
            fields.append(("url", _escape_bibtex(url)))
        if abstract:
            fields.append(("abstract", _escape_bibtex(abstract)))
        if keywords:
            fields.append(("keywords", _escape_bibtex(", ".join(keywords))))

        body = ",\n".join([f"  {k} = {{{v}}}" for k, v in fields])
        entries.append(f"@{entry_type}{{{key},\n{body}\n}}")

    return "\n\n".join(entries).strip() + ("\n" if entries else "")


def captures_to_ris(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for r in rows:
        dto = build_capture_dto_from_row(r)

        title = str(dto.get("title") or "").strip()
        url = str(dto.get("url") or "").strip()
        doi = str(dto.get("doi") or "").strip()
        journal = str(dto.get("container_title") or "").strip()

        year_i = dto.get("year", None)
        year_i = year_i if isinstance(year_i, int) else None

        keywords = dto.get("keywords") or []
        authors = dto.get("authors") or []
        abstract = _norm_abstract(str(dto.get("abstract") or ""))

        ty = "JOUR" if journal else "GEN"
        lines.append(f"TY  - {ty}")
        if title:
            lines.append(f"TI  - {title}")
        for a in authors:
            lines.append(f"AU  - {a}")
        if journal:
            lines.append(f"JO  - {journal}")
        if year_i:
            lines.append(f"PY  - {year_i}")
        if doi:
            lines.append(f"DO  - {doi}")
        if url:
            lines.append(f"UR  - {url}")
        if abstract:
            lines.append(f"AB  - {abstract}")
        for kw in keywords:
            k = str(kw).strip()
            if k:
                lines.append(f"KW  - {k}")
        lines.append("ER  -")
        lines.append("")

    return "\n".join(lines).strip() + ("\n" if lines else "")
