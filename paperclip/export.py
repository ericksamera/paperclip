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
        v = json.loads(row.get("meta_json") or "{}")
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _norm_authors(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, str):
        val = [val]
    if not isinstance(val, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for a in val:
        s = str(a).strip()
        if not s:
            continue
        k = s.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _norm_abstract(val: Any) -> str:
    if val is None:
        return ""
    if not isinstance(val, str):
        val = str(val)
    return re.sub(r"\s+", " ", val).strip()


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

        authors = _norm_authors(meta.get("authors"))
        abstract = _norm_abstract(meta.get("abstract"))

        entry_type = "article" if journal else "misc"
        key = _bibtex_key(cid, year_i)

        fields: list[tuple[str, str]] = []
        fields.append(("title", _escape_bibtex(title or "Untitled")))
        if authors:
            # BibTeX expects "and" between authors
            fields.append(("author", _escape_bibtex(" and ".join(authors))))
        if journal:
            fields.append(("journal", _escape_bibtex(journal)))
        if year_i:
            fields.append(("year", str(year_i)))
        if doi:
            fields.append(("doi", _escape_bibtex(doi)))
        if url:
            fields.append(("url", _escape_bibtex(url)))
        if abstract:
            fields.append(("abstract", _escape_bibtex(abstract)))
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

        authors = _norm_authors(meta.get("authors"))
        abstract = _norm_abstract(meta.get("abstract"))

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
        lines.append("")  # blank line between records

    return "\n".join(lines).strip() + ("\n" if lines else "")
