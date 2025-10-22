# packages/paperclip-parser/paperclip_parser/tables.py
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup, Tag

_WS_RE = re.compile(r"[ \t\r\f\v]+")


def _clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = (
        s.replace("\xa0", " ")
        .replace("\u2009", " ")
        .replace("\u2002", " ")
        .replace("\u2003", " ")
    )
    s = _WS_RE.sub(" ", s)
    return s.strip()


def _cell_text(cell: Tag) -> str:
    for hr in cell.find_all("hr"):
        hr.decompose()
    return _clean_text(cell.get_text(" ", strip=True))


def _pad_to(row: List[str], n_cols: int) -> List[str]:
    if len(row) < n_cols:
        row.extend([""] * (n_cols - len(row)))
    return row


def _expand_rows(trs: List[Tag]) -> List[List[str]]:
    rows: List[List[str]] = []
    occupied: Dict[int, int] = {}  # col_index -> rows remaining (from rowspan)

    for tr in trs:
        row: List[str] = []
        col_idx = 0

        def advance_to_free():
            nonlocal col_idx
            while occupied.get(col_idx, 0) > 0:
                row.append("")
                col_idx += 1

        cells = tr.find_all(["th", "td"], recursive=False)
        for cell in cells:
            advance_to_free()
            try:
                colspan = int(cell.get("colspan", 1))
            except ValueError:
                colspan = 1
            try:
                rowspan = int(cell.get("rowspan", 1))
            except ValueError:
                rowspan = 1

            text = _cell_text(cell)
            row.append(text)
            if colspan > 1:
                row.extend([""] * (colspan - 1))

            if rowspan > 1:
                for j in range(col_idx, col_idx + colspan):
                    occupied[j] = max(occupied.get(j, 0), rowspan - 1)

            col_idx += colspan

        rows.append(row)
        # tick rowspans down
        occupied = {k: v - 1 for k, v in occupied.items() if v - 1 > 0}

    n_cols = max((len(r) for r in rows), default=0)
    rows = [_pad_to(r, n_cols) for r in rows]
    return rows


def _collect_title_caption_id(table: Tag) -> Dict[str, Optional[str]]:
    # nearest ancestor with an id (pmc often wraps <table> in <section id="T1">)
    anc_with_id = table.find_parent(lambda t: isinstance(t, Tag) and t.has_attr("id"))
    table_id = anc_with_id.get("id") if anc_with_id else None

    # prefer nearest heading in the same wrapper, if source line info exists
    title = None
    wrap = anc_with_id or table.parent
    if wrap:
        heads = wrap.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        tline = getattr(table, "sourceline", None)
        for h in reversed(heads):
            hline = getattr(h, "sourceline", None)
            if hline is not None and tline is not None and hline <= tline:
                title = _clean_text(h.get_text(" ", strip=True))
                break
        if not title and heads:
            title = _clean_text(heads[0].get_text(" ", strip=True))

    # caption: nearby .caption/figcaption
    caption = None
    candidates: List[Tag] = []
    for sib in (table.previous_sibling, table.next_sibling):
        if isinstance(sib, Tag):
            candidates.append(sib)
    if wrap:
        candidates.extend(wrap.find_all(["div", "figcaption"], class_=["caption"]))
    for cand in candidates:
        if isinstance(cand, Tag) and (
            "caption" in (cand.get("class") or []) or cand.name == "figcaption"
        ):
            cap_text = cand.get_text(" ", strip=True)
            if cap_text:
                caption = _clean_text(cap_text)
                break

    # source link (e.g., "Open in a new tab")
    source_link = None
    for sib in table.next_siblings:
        if isinstance(sib, Tag):
            a = sib.find("a", href=True)
            if a and a.get_text(strip=True):
                source_link = a["href"]
                break

    return {
        "id": table_id,
        "title": title,
        "caption": caption,
        "source_link": source_link,
    }


def _select_trs(table: Tag) -> Dict[str, List[Tag]]:
    thead_trs = []
    tbody_trs = []
    thead = table.find("thead")
    if thead:
        thead_trs = thead.find_all("tr")
    tbodies = table.find_all("tbody")
    if tbodies:
        for tb in tbodies:
            tbody_trs.extend(tb.find_all("tr"))
    else:
        all_trs = table.find_all("tr")
        if thead_trs:
            head_set = set(thead_trs)
            tbody_trs = [tr for tr in all_trs if tr not in head_set]
        else:
            tbody_trs = all_trs
    return {"thead": thead_trs, "tbody": tbody_trs}


def _compose_headers(
    header_rows: List[List[str]], body_rows: List[List[str]]
) -> List[str]:
    if header_rows:
        n_cols = max(len(r) for r in header_rows)
        headers: List[str] = []
        for c in range(n_cols):
            parts = [r[c] for r in header_rows if c < len(r) and r[c]]
            name = " / ".join(parts).strip() or f"Column {c+1}"
            if c == 0 and (not name or name.startswith("Column ")):
                name = "Feature"
            headers.append(name)
        return headers

    if body_rows:
        first = body_rows[0]
        non_empty_ratio = sum(1 for x in first if x) / max(1, len(first))
        if non_empty_ratio >= 0.75:
            hdrs = [x or f"Column {i+1}" for i, x in enumerate(first)]
            if hdrs and (not hdrs[0] or hdrs[0].startswith("Column ")):
                hdrs[0] = "Feature"
            return hdrs

    n_cols = max((len(r) for r in body_rows), default=0)
    headers = [f"Column {i+1}" for i in range(n_cols)]
    if headers:
        headers[0] = "Feature"
    return headers


def _parse_table(table: Tag) -> Dict[str, Any]:
    meta = _collect_title_caption_id(table)
    tr_groups = _select_trs(table)
    header_rows = _expand_rows(tr_groups["thead"]) if tr_groups["thead"] else []
    body_rows = _expand_rows(tr_groups["tbody"]) if tr_groups["tbody"] else []
    headers = _compose_headers(header_rows, body_rows)

    width = max(len(headers), max((len(r) for r in body_rows), default=0))
    if len(headers) < width:
        headers.extend([f"Column {i+1}" for i in range(len(headers), width)])
    body_rows = [_pad_to(list(r), width) for r in body_rows]

    records: List[Dict[str, str]] = []
    for r in body_rows:
        records.append({headers[i]: r[i] for i in range(width)})

    return {
        "id": meta.get("id"),
        "title": meta.get("title"),
        "caption": meta.get("caption"),
        "source_link": meta.get("source_link"),
        "columns": headers,
        "rows": body_rows,
        "records": records,
    }


def extract_tables(html_fragment: str) -> List[Dict[str, Any]]:
    """Find and normalize all <table> elements inside an HTML fragment."""
    if not html_fragment:
        return []
    soup = BeautifulSoup(html_fragment, "html.parser")
    results: List[Dict[str, Any]] = []
    for t in soup.find_all("table"):
        try:
            results.append(_parse_table(t))
        except Exception as e:  # keep a record rather than failing entirely
            results.append(
                {
                    "id": None,
                    "title": None,
                    "caption": None,
                    "source_link": None,
                    "columns": [],
                    "rows": [],
                    "records": [],
                    "error": f"{type(e).__name__}: {e}",
                }
            )
    return results
