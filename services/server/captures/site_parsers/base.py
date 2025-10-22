# services/server/captures/site_parsers/base.py
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import cast

from bs4 import Tag

from paperclip.utils import norm_doi  # noqa: F401 (kept for future helpers)

# ======================================================================================
# Shared regexes and tiny normalizers
# ======================================================================================
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def collapse_spaces(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def norm(s: str | None) -> str:
    return (s or "").strip()


# A simple, shared text normalizer alias
def txt(x: str | None) -> str:
    return collapse_spaces(x)


def heading_text(h: Tag | None) -> str:
    """Return visible heading text with outline numbers removed (e.g., '2.4)' prefix)."""
    if not h:
        return ""
    t = collapse_spaces(h.get_text(" ", strip=True))
    return re.sub(r"^\s*\d+(?:\.\d+)*\s*[\.\)]?\s*", "", t)


def dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for k in items:
        lk = (k or "").strip().lower()
        if lk and lk not in seen:
            seen.add(lk)
            out.append(k.strip())
    return out


def is_heading(tag: Tag | None) -> bool:
    return isinstance(tag, Tag) and tag.name in {"h2", "h3", "h4"}


# ======================================================================================
# Paragraph collectors used by multiple site parsers
# ======================================================================================
# ScienceDirect uses <div id="p0025" class="u-margin-s-bottom">...</div> for paragraphs:
_SD_PARA_ID = re.compile(r"^p\d{3,}$", re.I)


def looks_like_para_div(el: Tag) -> bool:
    if not isinstance(el, Tag) or el.name != "div":
        return False
    did = (el.get("id") or "").lower()
    cls = " ".join(el.get("class") or []).lower()
    return bool(
        _SD_PARA_ID.match(did)
        or "u-margin" in cls
        or "para" in cls
        or "paragraph" in cls
    )


def collect_sd_paragraphs(sec: Tag) -> list[str]:
    """
    ScienceDirect-style paragraphs directly under a <section>, keeping list items too.
    (Direct children only; used for structured <section> trees.)
    """
    out: list[str] = []
    # Normal <p> children (few SD pages have them)
    for p in sec.find_all("p", recursive=False):
        t = collapse_spaces(p.get_text(" ", strip=True))
        if t:
            out.append(t)
    # SD paragraph DIVs: id="p0025" / class*="u-margin"
    for d in sec.find_all("div", recursive=False):
        if not looks_like_para_div(d):
            continue
        # lists inside paragraph divs
        lis = [
            collapse_spaces(li.get_text(" ", strip=True))
            for li in d.find_all("li", recursive=True)
        ]
        lis = [x for x in lis if x and len(x) > 1]
        if lis:
            out.extend(lis)
            continue
        t = collapse_spaces(d.get_text(" ", strip=True))
        if t:
            out.append(t)
    # direct UL/OL children at section root
    for ul in sec.find_all(["ul", "ol"], recursive=False):
        for li in ul.find_all("li", recursive=True):
            t = collapse_spaces(li.get_text(" ", strip=True))
            if t:
                out.append(t)
    return out


def collect_paragraphs_subtree(root: Tag) -> list[str]:
    """
    Collect paragraph-like blocks anywhere under 'root' (not just direct children).
    Order is stable; duplicates avoided when a SD paragraph DIV also contains <p>.
    """
    out: list[str] = []
    # 1) List items anywhere
    for ul in root.find_all(["ul", "ol"]):
        for li in ul.find_all("li", recursive=True):
            t = collapse_spaces(li.get_text(" ", strip=True))
            if t:
                out.append(t)
    # 2) SD-style paragraph DIVs that do NOT contain <p> (otherwise <p> will cover it)
    for d in root.find_all("div"):
        if looks_like_para_div(d):
            if d.find("p"):
                continue
            # if it had <li>, they were already captured in step 1 - only take plain text here
            t = collapse_spaces(d.get_text(" ", strip=True))
            if t:
                out.append(t)
    # 3) Plain paragraphs anywhere
    for p in root.find_all("p"):
        t = collapse_spaces(p.get_text(" ", strip=True))
        if t:
            out.append(t)
    return out


def paras_between(head: Tag, next_head: Tag | None) -> list[str]:
    """
    Collect paragraph-like blocks that appear between a heading and the next heading.
    Handles:
      • direct <p> siblings
      • lists
      • SD-style paragraph DIVs
      • nested <p> inside any sibling subtree
    """
    out: list[str] = []
    sib = head.next_sibling
    while sib and sib is not next_head:
        if isinstance(sib, Tag):
            if is_heading(sib):
                break
            # Pull paragraphs from the whole subtree under this sibling.
            out.extend(collect_paragraphs_subtree(sib))
        sib = sib.next_sibling
    return out


# ======================================================================================
# NEW: Shared keyword + section helpers to de-duplicate site parsers
# ======================================================================================
KEYWORDS_PREFIX_RX = re.compile(r"^\s*Keywords?\s*[::-]?\s*", re.I)


def split_keywords_block(s: str) -> list[str]:
    """
    Split a 'Keywords: a, b; c/d' block into clean tokens.
    Keeps parentheses content; collapses delim varieties; trims ornaments.
    """
    s = KEYWORDS_PREFIX_RX.sub("", s or "")
    # Normalize delimiters to commas, then split.
    s = re.sub(r"[;\n\r/]+", ",", s)
    parts = [p.strip(" .,:;/-") for p in s.split(",")]
    return [p for p in parts if p and len(p) > 1]


def next_heading(node: Tag, levels: Iterable[str] = ("h2", "h3", "h4")) -> Tag | None:
    cur = node.next_sibling
    while cur:
        if isinstance(cur, Tag) and (cur.name or "").lower() in {
            lvl.lower() for lvl in levels
        }:
            return cur
        cur = getattr(cur, "next_sibling", None)
    return None


def _has_ancestor_matching(
    tag: Tag, root: Tag, predicate: Callable[[Tag], bool]
) -> bool:
    cur = tag.parent
    while isinstance(cur, Tag) and cur is not root:
        if predicate(cur):
            return True
        cur = cur.parent
    return False


def collect_paras_excluding(
    root: Tag, is_subsection_container: Callable[[Tag], bool]
) -> list[str]:
    """
    Collect <p>/<li> that belong to `root`, skipping those inside nested blocks
    recognized by `is_subsection_container`. If nothing found AND there are no
    such nested blocks, fall back to subtree text.
    """
    out: list[str] = []
    has_sub = any(
        is_subsection_container(c) for c in root.find_all(True, recursive=False)
    )
    for p in root.find_all("p"):
        if _has_ancestor_matching(p, root, is_subsection_container):
            continue
        t = collapse_spaces(p.get_text(" ", strip=True))
        if t:
            out.append(t)
    for li in root.find_all("li"):
        if _has_ancestor_matching(li, root, is_subsection_container):
            continue
        t = collapse_spaces(li.get_text(" ", strip=True))
        if t:
            out.append(t)
    if not out and not has_sub:
        out = [t for t in collect_paragraphs_subtree(root) if t]
    return out


def dedupe_section_nodes(nodes: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, int]] = set()
    uniq: list[dict[str, object]] = []
    for n in nodes or []:
        children = cast(list[object], n.get("children") or [])
        key = (str(n.get("title") or "").strip().lower(), len(children))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(n)
    return uniq


# ======================================================================================
# Author tokenization / normalization used by some sites
# ======================================================================================
def tokenize_authors_csv(s: str) -> list[str]:
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out: list[str] = []
    i = 0
    while i < len(parts):
        cur = parts[i]
        if re.search(r"[A-Z]\.", cur) and re.search(r"\s[A-Z][a-zA-Z''\-]+$", cur):
            out.append(cur)
            i += 1
        elif (
            re.fullmatch(r"(?:[A-Z]\.){1,4}", cur)
            and i + 1 < len(parts)
            and re.fullmatch(r"[A-Z][a-zA-Z''\-]+", parts[i + 1])
        ):
            out.append(cur + " " + parts[i + 1])
            i += 2
        else:
            out.append(cur)
            i += 1
    return out


def authors_initials_first_to_surname_initials(auths: list[str]) -> list[str]:
    out: list[str] = []
    for a in auths:
        a = collapse_spaces(a)
        m = re.fullmatch(
            r"((?:[A-Z]\.){1,4})\s+([A-Z][a-zA-Z''\-]+)", a
        )  # "A.T. Vincent"
        if m:
            out.append(f"{m.group(2)}, {m.group(1)}")
            continue
        m = re.fullmatch(
            r"([A-Z][a-zA-Z''\-]+),\s*((?:[A-Z]\.){1,4})", a
        )  # "Vincent, A.T."
        if m:
            out.append(a)
            continue
        if a:
            out.append(a)
    return out


# ======================================================================================
# Generic <li> reference helpers (used by PMC/generic)
# ======================================================================================
def extract_from_li(li: Tag) -> dict[str, str]:
    cite = li.find("cite")
    raw = (
        cite.get_text(" ", strip=True) if cite else li.get_text(" ", strip=True)
    ) or ""
    href_doi = ""
    for a in li.find_all("a", href=True):
        m = DOI_RE.search(a["href"])
        if m:
            href_doi = m.group(0)
            break
    text_doi = ""
    m = DOI_RE.search(raw)
    if m:
        text_doi = m.group(0)
    my = YEAR_RE.search(raw)
    year = my.group(0) if my else ""
    return {"raw": raw, "doi": href_doi or text_doi, "issued_year": year}


# ======================================================================================
# Raw-text best effort reference parsing (kept as-is, shared by all sites)
# ======================================================================================
def parse_raw_reference(raw: str) -> dict[str, object]:
    text = collapse_spaces(raw)
    text = re.sub(r"^[\[\(]?\d+[\]\)\.\:]\s*", "", text)
    out: dict[str, object] = {"raw": raw, "doi": ""}
    jmatch = re.search(
        r"(?P<journal>[A-Za-z][A-Za-z\.\s&\-]+?),\s*(?P<vol>\d{1,4})\s*\((?P<year>\d{4})\)",
        text,
    )
    jstart = jmatch.start() if jmatch else -1
    authors: list[str] = []
    pos = 0
    while pos < len(text):
        m1 = re.match(r"(?:[A-Z](?:\.[A-Z])+\.?)\s+([A-Z][a-zA-Z''\-]+)", text[pos:])
        m2 = re.match(r"([A-Z][a-zA-Z''\-]+),\s*(?:[A-Z](?:\.[A-Z])+\.?)", text[pos:])
        used = None
        if m1:
            surname = m1.group(1)
            m1_initials = re.match(r"((?:[A-Z]\.){1,4})", text[pos:])
            if m1_initials:
                authors.append(f"{surname}, {m1_initials.group(1)}")
            used = m1
        elif m2:
            surname = m2.group(1)
            m2_initials = re.match(r".*?,\s*((?:[A-Z]\.){1,4})", text[pos:])
            if m2_initials:
                authors.append(f"{surname}, {m2_initials.group(1)}")
            used = m2
        else:
            break
        pos += used.end()
        mcomma = re.match(r",\s*", text[pos:])
        if mcomma:
            pos += mcomma.end()
        if jstart != -1 and pos >= jstart:
            break
    if authors:
        out["authors"] = authors
    title_end = jstart if jstart != -1 else len(text)
    title = text[pos:title_end].strip(" .;,-")
    if title:
        out["title"] = title
    if jmatch:
        out["container_title"] = collapse_spaces(jmatch.group("journal"))
        out["volume"] = jmatch.group("vol")
        out["issued_year"] = jmatch.group("year")
    else:
        my = YEAR_RE.search(text)
        if my:
            out["issued_year"] = my.group(0)
    return out


def augment_from_raw(d: dict[str, str]) -> dict[str, object]:
    parsed = parse_raw_reference(d.get("raw", ""))
    out: dict[str, object] = dict(d)
    for k, v in parsed.items():
        if k not in out or not out[k]:
            out[k] = v
    return out
