from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

from captures.models import Capture
from captures.types import CSL
from paperclip.utils import norm_doi
from captures.views.common import _journal_full, _author_list  # reuse project helpers


def _ascii_slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    s = re.sub(r"-{2,}", "-", s)
    return s or "item"


def _bibtex_authors(c: Capture) -> str:
    csl: CSL | Mapping[str, Any] = c.csl or {}
    meta = c.meta or {}
    items: list[str] = []

    try:
        csl_auth = (csl or {}).get("author")  # type: ignore[index]
    except Exception:
        csl_auth = None
    if isinstance(csl_auth, list):
        for a in csl_auth:
            if isinstance(a, dict):
                fam = (
                    a.get("family") or a.get("last") or a.get("literal") or ""
                ).strip()
                giv = (a.get("given") or a.get("first") or "").strip()
                if fam or giv:
                    items.append(f"{fam}, {giv}".strip().rstrip(","))

    if not items:
        for s in _author_list(meta, csl):
            s = (s or "").strip()
            if "," in s:
                items.append(s)
            else:
                parts = s.split()
                if len(parts) >= 2:
                    fam = parts[-1]
                    giv = " ".join(parts[:-1])
                    items.append(f"{fam}, {giv}".strip().rstrip(","))
                elif s:
                    items.append(s)

    out, seen = [], set()
    for x in items:
        k = x.lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x)
    return " and ".join(out)


def _bibtex_escape(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ").replace("\r", " ").strip()
    return s.replace("{", "\\{").replace("}", "\\}")


def bibtex_entry_for(c: Capture) -> str:
    meta = c.meta or {}
    csl: CSL | Mapping[str, Any] = c.csl or {}

    title = (
        c.title
        or meta.get("title")
        or ((csl.get("title") if isinstance(csl, Mapping) else "") or "")
        or c.url
        or ""
    ).strip() or "(Untitled)"
    journal = _journal_full(meta, csl)
    doi = norm_doi(
        c.doi or meta.get("doi") or (csl.get("DOI") if isinstance(csl, Mapping) else "")
    )
    year = str(meta.get("year") or meta.get("publication_year") or c.year or "").strip()

    volume = (
        str(
            (csl.get("volume") if isinstance(csl, Mapping) else "")
            or meta.get("volume")
            or ""
        )
        or ""
    )
    issue = (
        str(
            (csl.get("issue") if isinstance(csl, Mapping) else "")
            or meta.get("issue")
            or ""
        )
        or ""
    )
    pages = (
        str(
            (csl.get("page") if isinstance(csl, Mapping) else "")
            or meta.get("pages")
            or ""
        )
        or ""
    )
    url = c.url or ""

    entry_type = "article" if journal else "misc"

    fam = ""
    authors_for_key = _bibtex_authors(c)
    if authors_for_key:
        fam = authors_for_key.split(" and ")[0].split(",", 1)[0]
    first_word = (
        re.sub(r"[^A-Za-z0-9]+", "", title.split()[0]) if title.split() else "item"
    )
    key = _ascii_slug(f"{fam or 'anon'}-{year or 'na'}-{first_word}")

    fields = []
    fields.append(f"title = {{{_bibtex_escape(title)}}}")
    if authors_for_key:
        fields.append(f"author = {{{_bibtex_escape(authors_for_key)}}}")
    if journal:
        fields.append(f"journal = {{{_bibtex_escape(journal)}}}")
    if year:
        fields.append(f"year = {{{_bibtex_escape(year)}}}")
    if volume:
        fields.append(f"volume = {{{_bibtex_escape(volume)}}}")
    if issue:
        fields.append(f"number = {{{_bibtex_escape(issue)}}}")
    if pages:
        fields.append(f"pages = {{{_bibtex_escape(pages)}}}")
    if doi:
        fields.append(f"doi = {{{_bibtex_escape(doi)}}}")
    if url:
        fields.append(f"url = {{{_bibtex_escape(url)}}}")

    inner = ",\n  ".join(fields)
    return f"@{entry_type}{{{key},\n  {inner}\n}}"


def ris_lines_for(c: Capture) -> list[str]:
    meta = c.meta or {}
    csl: CSL | Mapping[str, Any] = c.csl or {}

    journal = _journal_full(meta, csl)
    year = str(meta.get("year") or meta.get("publication_year") or c.year or "").strip()
    doi = norm_doi(
        c.doi or meta.get("doi") or (csl.get("DOI") if isinstance(csl, Mapping) else "")
    )
    url = c.url or ""
    volume = (
        str(
            (csl.get("volume") if isinstance(csl, Mapping) else "")
            or meta.get("volume")
            or ""
        )
        or ""
    )
    issue = (
        str(
            (csl.get("issue") if isinstance(csl, Mapping) else "")
            or meta.get("issue")
            or ""
        )
        or ""
    )
    pages = (
        str(
            (csl.get("page") if isinstance(csl, Mapping) else "")
            or meta.get("pages")
            or ""
        )
        or ""
    )
    sp, ep = "", ""
    m = re.match(r"^\s*(\d+)\s*[-–—]\s*(\d+)\s*$", pages)
    if m:
        sp, ep = m.group(1), m.group(2)

    ty = "JOUR" if journal else "GEN"
    lines = [f"TY  - {ty}"]
    for a in (_bibtex_authors(c) or "").split(" and "):
        a = a.strip()
        if a:
            lines.append(f"AU  - {a}")
    title = (
        c.title
        or meta.get("title")
        or ((csl.get("title") if isinstance(csl, Mapping) else "") or "")
        or c.url
        or ""
    ).strip()
    if title:
        lines.append(f"TI  - {title}")
    if year:
        lines.append(f"PY  - {year}")
    if journal:
        lines.append(f"JO  - {journal}")
    if volume:
        lines.append(f"VL  - {volume}")
    if issue:
        lines.append(f"IS  - {issue}")
    if sp:
        lines.append(f"SP  - {sp}")
    if ep:
        lines.append(f"EP  - {ep}")
    if doi:
        lines.append(f"DO  - {doi}")
    if url:
        lines.append(f"UR  - {url}")
    lines.append("ER  - ")
    return lines
