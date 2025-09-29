# services/server/captures/site_parsers/base.py
from __future__ import annotations
from typing import Dict, List
import re
from bs4 import BeautifulSoup
from paperclip.utils import norm_doi

DOI_RE  = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

def collapse_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()

def norm(s: str | None) -> str:
    return (s or "").strip()

# ----- author tokenization / normalization -----

def tokenize_authors_csv(s: str) -> List[str]:
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out: List[str] = []
    i = 0
    while i < len(parts):
        cur = parts[i]
        if re.search(r"[A-Z]\.", cur) and re.search(r"\s[A-Z][a-zA-Z'’\-]+$", cur):
            out.append(cur); i += 1
        elif re.fullmatch(r"(?:[A-Z]\.){1,4}", cur) and i + 1 < len(parts) and re.fullmatch(r"[A-Z][a-zA-Z'’\-]+", parts[i + 1]):
            out.append(cur + " " + parts[i + 1]); i += 2
        else:
            out.append(cur); i += 1
    return out

def authors_initials_first_to_surname_initials(auths: List[str]) -> List[str]:
    out: List[str] = []
    for a in auths:
        a = collapse_spaces(a)
        m = re.fullmatch(r"((?:[A-Z]\.){1,4})\s+([A-Z][a-zA-Z'’\-]+)", a)  # "A.T. Vincent"
        if m:
            out.append(f"{m.group(2)}, {m.group(1)}"); continue
        m = re.fullmatch(r"([A-Z][a-zA-Z'’\-]+),\s*((?:[A-Z]\.){1,4})", a)  # "Vincent, A.T."
        if m:
            out.append(a); continue
        if a:
            out.append(a)
    return out

# ----- generic LI/cite helpers -----

def extract_from_li(li) -> Dict[str, str]:
    cite = li.find("cite")
    raw = (cite.get_text(" ", strip=True) if cite else li.get_text(" ", strip=True)) or ""
    href_doi = ""
    for a in li.find_all("a", href=True):
        m = DOI_RE.search(a["href"])
        if m:
            href_doi = m.group(0); break
    text_doi = ""
    m = DOI_RE.search(raw)
    if m: text_doi = m.group(0)
    my = YEAR_RE.search(raw)
    year = my.group(0) if my else ""
    return {"raw": raw, "doi": href_doi or text_doi, "issued_year": year}

# ----- raw-text best effort -----

def parse_raw_reference(raw: str) -> Dict[str, object]:
    text = collapse_spaces(raw)
    text = re.sub(r"^[\[\(]?\d+[\]\)\.\:]\s*", "", text)
    out: Dict[str, object] = {"raw": raw, "doi": ""}

    jmatch = re.search(r"(?P<journal>[A-Za-z][A-Za-z\.\s&\-]+?),\s*(?P<vol>\d{1,4})\s*\((?P<year>\d{4})\)", text)
    jstart = jmatch.start() if jmatch else -1

    authors: List[str] = []
    pos = 0
    while pos < len(text):
        m1 = re.match(r"(?:[A-Z](?:\.[A-Z])+\.?)\s+([A-Z][a-zA-Z'’\-]+)", text[pos:])
        m2 = re.match(r"([A-Z][a-zA-Z'’\-]+),\s*(?:[A-Z](?:\.[A-Z])+\.?)", text[pos:])
        used = None
        if m1:
            surname = m1.group(1)
            initials = re.match(r"((?:[A-Z]\.){1,4})", text[pos:]).group(1)  # type: ignore[union-attr]
            authors.append(f"{surname}, {initials}"); used = m1
        elif m2:
            surname = m2.group(1)
            initials = re.match(r".*?,\s*((?:[A-Z]\.){1,4})", text[pos:]).group(1)  # type: ignore[union-attr]
            authors.append(f"{surname}, {initials}"); used = m2
        else:
            break
        pos += used.end()
        mcomma = re.match(r",\s*", text[pos:])
        if mcomma: pos += mcomma.end()
        if jstart != -1 and pos >= jstart: break

    if authors: out["authors"] = authors

    title_end = jstart if jstart != -1 else len(text)
    title = text[pos:title_end].strip(" .;,-")
    if title: out["title"] = title

    if jmatch:
        out["container_title"] = collapse_spaces(jmatch.group("journal"))
        out["volume"] = jmatch.group("vol")
        out["issued_year"] = jmatch.group("year")
    else:
        my = YEAR_RE.search(text)
        if my: out["issued_year"] = my.group(0)
    return out

def augment_from_raw(d: Dict[str, str]) -> Dict[str, object]:
    parsed = parse_raw_reference(d.get("raw", ""))
    out: Dict[str, object] = dict(d)
    for k, v in parsed.items():
        if k not in out or not out[k]:  # type: ignore[index]
            out[k] = v
    return out
