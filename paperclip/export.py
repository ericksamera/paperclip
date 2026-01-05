from __future__ import annotations

import json
import re
from typing import Any


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


def _meta_from_row(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(row.get("meta_json") or "{}")
    except Exception:
        return {}


def captures_to_bibtex(rows: list[dict[str, Any]]) -> str:
    entries: list[str] = []
    for r in rows:
        cid = str(r.get("id") or "")
        title = str(r.get("title") or "").strip()
        url = str(r.get("url") or "").strip()
        doi = str(r.get("doi") or "").strip()
        year = r.get("year", None)
        try:
            year_i = int(year) if year is not None else None
        except Exception:
            year_i = None
        journal = str(r.get("container_title") or "").strip()

        meta = _meta_from_row(r)
        keywords = meta.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [keywords]
        if not isinstance(keywords, list):
            keywords = []

        entry_type = "article" if journal else "misc"
        key = _bibtex_key(cid, year_i)

        fields: list[tuple[str, str]] = []
        fields.append(("title", _escape_bibtex(title or "Untitled")))
        if journal:
            fields.append(("journal", _escape_bibtex(journal)))
        if year_i:
            fields.append(("year", str(year_i)))
        if doi:
            fields.append(("doi", _escape_bibtex(doi)))
        if url:
            fields.append(("url", _escape_bibtex(url)))
        if keywords:
            fields.append(
                (
                    "keywords",
                    _escape_bibtex(
                        ", ".join(str(x) for x in keywords if str(x).strip())
                    ),
                )
            )

        body = ",\n".join([f"  {k} = {{{v}}}" for k, v in fields])
        entries.append(f"@{entry_type}{{{key},\n{body}\n}}")

    return "\n\n".join(entries).strip() + ("\n" if entries else "")


def captures_to_ris(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for r in rows:
        title = str(r.get("title") or "").strip()
        url = str(r.get("url") or "").strip()
        doi = str(r.get("doi") or "").strip()
        journal = str(r.get("container_title") or "").strip()

        year = r.get("year", None)
        try:
            year_i = int(year) if year is not None else None
        except Exception:
            year_i = None

        meta = _meta_from_row(r)
        keywords = meta.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [keywords]
        if not isinstance(keywords, list):
            keywords = []

        ty = "JOUR" if journal else "GEN"
        lines.append(f"TY  - {ty}")
        if title:
            lines.append(f"TI  - {title}")
        if journal:
            lines.append(f"JO  - {journal}")
        if year_i:
            lines.append(f"PY  - {year_i}")
        if doi:
            lines.append(f"DO  - {doi}")
        if url:
            lines.append(f"UR  - {url}")
        for kw in keywords:
            k = str(kw).strip()
            if k:
                lines.append(f"KW  - {k}")
        lines.append("ER  -")
        lines.append("")  # blank line between records

    return "\n".join(lines).strip() + ("\n" if lines else "")
